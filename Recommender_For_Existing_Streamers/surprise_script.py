import pandas as pd
import numpy as np
from collections import defaultdict
import pickle
import surprise
from surprise import Dataset, accuracy, Reader, NMF, NormalPredictor, BaselineOnly, CoClustering, SlopeOne, SVD, KNNBaseline
from surprise.model_selection import GridSearchCV, cross_validate, train_test_split

# First step is taking the input from the streamer concerning their existing behavior:

streamer_name = input('What is your streamer name? ')
streamer_genres = list(input ('Which game genres do you currently stream? ').split(', '))
streamer_games = list(input ('Which games do you currently stream? ').split(', '))

#First, we make sure our records match their inputs and augment as needed:
with open( "./Data/genres.pkl", "rb" ) as f:
    genres = pickle.load(f)
# genres = pickle.load( open( "./Data/genres.pkl", "rb" ) )

# algo_genre_user = pickle.load( open( "./Data/SlopeOne_genre_model.pkl", "rb" ) )
with open( "./Data/SlopeOne_genre_model.pkl", "rb" ) as f:
    algo_genre_base = pickle.load(f)

with open( "./Data/games.pkl", "rb" ) as f:
    games = pickle.load(f)

with open( "./Data/BaselineOnly_game_model.pkl", "rb" ) as f:
    algo_game_base = pickle.load(f)

def display_current_genres(streamer_name):
    user_genres = list(genres[genres['user_name']==streamer_name]['game_genres'])
    return user_genres

recorder_genre_list = display_current_genres(streamer_name)
full_genres = list(set(recorder_genre_list + streamer_genres))

def display_current_games(streamer_name):
    user_games = list(games[games['user_name']==streamer_name]['game_name'])
    return user_games

recorder_game_list = display_current_games(streamer_name)
full_games = list(set(recorder_game_list + streamer_games))

#Predicting Similar Genres/Games Based on User experience (user-based similarity) #
def get_top_n(predictions, n=10):
    top_n = defaultdict(list)
    for uid, iid, true_r, est, _ in predictions:
        top_n[uid].append((iid, est))

    # Then sort the predictions for each user and retrieve the k highest ones.
    for uid, user_ratings in top_n.items():
        user_ratings.sort(key=lambda x: x[1], reverse=True)
        top_n[uid] = user_ratings[:n]

    return top_n

genre_iids = genres['game_genres'].unique()
genre_iids_to_predict = np.setdiff1d(genre_iids, full_genres, assume_unique = True)
genre_testset_personal = [[streamer_name, iid, 4.] for iid in genre_iids_to_predict]
genre_personal_predictions = algo_genre_base.test(genre_testset_personal)
genre_top_n = get_top_n(genre_personal_predictions)
for uid, genre_user_ratings in genre_top_n.items():
    genre_user_based_list = [iid for (iid, _) in genre_user_ratings]
    #print("The recommended genres you're currently not streaming are:"+ str([iid for (iid, _) in user_ratings]))


game_iids = games['game_name'].unique()
game_iids_to_predict = np.setdiff1d(game_iids, full_games, assume_unique = True)
game_testset_personal = [[streamer_name, iid, 4.] for iid in game_iids_to_predict]
game_personal_predictions = algo_game_base.test(game_testset_personal)
game_top_n = get_top_n(game_personal_predictions)
for uid, game_user_ratings in game_top_n.items():
    game_user_based_list = [iid for (iid, _) in game_user_ratings]
    #print("The recommended games you're currently not streaming are:"+ str([iid for (iid, _) in user_ratings]))




#Predicting Similar Genres/Games based on genre similarity to each other (item-based similarity)
genre_group = pickle.load( open( "./Data/genre_group.pkl", "rb" ) )
reader = Reader(rating_scale=(1, 5))
genre_data = Dataset.load_from_df(genre_group[['user_name', 'game_genres', 'mean']], reader)
genre_trainset = genre_data.build_full_trainset()

game_group = pickle.load( open( "./Data/game_group.pkl", "rb" ) )
reader = Reader(rating_scale=(1, 5))
game_data = Dataset.load_from_df(game_group[['user_name', 'game_name', 'mean']], reader)
game_trainset = game_data.build_full_trainset()


#Fit the KNN algorithm to the data
sim_options = {'name': 'pearson_baseline',
               'shrinkage': 0, 'user_based': False  # no shrinkage
               }
algo_genre_group = KNNBaseline(sim_options=sim_options, verbose = False)
algo_genre_group.fit(genre_trainset)


algo_game_group = KNNBaseline(sim_options=sim_options, verbose = False)
algo_game_group.fit(game_trainset)

#produce the list of genres/games needed to be evaluated

genre_inner_id_list = []
for genre in full_genres:
    inner = algo_genre_group.trainset.to_inner_iid(genre)
    genre_inner_id_list.append(inner)

game_inner_id_list = []
for game in full_games:
    inner = algo_game_group.trainset.to_inner_iid(game)
    game_inner_id_list.append(inner)

# get the list of neighbors for those genres/games

genre_neighbors_list = []
for inner in genre_inner_id_list:
    genre_neighbors = algo_genre_group.get_neighbors(inner, k=3)
    genre_neighbors_list.append(genre_neighbors)

game_neighbors_list = []
for inner in game_inner_id_list:
    game_neighbors = algo_game_group.get_neighbors(inner, k=3)
    game_neighbors_list.append(game_neighbors)

# prioritize closest neighbors to all original genres/games mentioned

genre_final_list = []
for item in genre_neighbors_list:
    genre_final_list.append(item[0])
    genre_final_list.append(item[1])

game_final_list = []
for item in game_neighbors_list:
    game_final_list.append(item[0])
    game_final_list.append(item[1])

# return results

genres = [algo_genre_group.trainset.to_raw_iid(iiid) for iiid in set(genre_final_list)]

games = [algo_game_group.trainset.to_raw_iid(iiid) for iiid in set(game_final_list)]
#print('The nearest neighbors of your current genres are:' + str(genres))
#print('The nearest neighbors of your current games are:' + str(games))

# combined outputs of both methods to produce results common in both
print("We recommend you stream the following genres: " + ', '.join(item for item in set(genres + genre_user_based_list)))
print("We recommend you stream the following games: " + ', '.join(item for item in set(games + game_user_based_list)))
