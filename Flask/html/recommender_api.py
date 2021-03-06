'''
Recommender API
'''
import pandas as pd
import numpy as np
from collections import defaultdict
import pickle
import surprise
from surprise import Dataset, accuracy, Reader, NMF, NormalPredictor, BaselineOnly, CoClustering, SlopeOne, SVD, KNNBaseline
from surprise.model_selection import GridSearchCV, cross_validate, train_test_split
from fuzzywuzzy import process

# First step is taking the input from the streamer concerning their existing behavior:

# streamer_name = input('What is your streamer name? ')
# streamer_genres = list(input ('Which game genres do you currently stream? ').split(', '))
# streamer_games = list(input ('Which games do you currently stream? ').split(', '))

#First, we make sure our records match their inputs and augment as needed:
def load_models():
    with open( "static/models/genres.pkl", "rb" ) as f:
        genres = pickle.load(f)

    with open( "static/models/SlopeOne_genre_model.pkl", "rb" ) as f:
        algo_genre_user = pickle.load(f)

    with open( "static/models/games.pkl", "rb" ) as f:
        games = pickle.load(f)

    with open( "static/models/BaselineOnly_game_model.pkl", "rb" ) as f:
        algo_game_user = pickle.load(f)
    return genres, algo_genre_user, games, algo_game_user

def display_current_genres(streamer_name,genres):
    user_genres = list(genres[genres['user_name']==streamer_name]['game_genres'])
    return user_genres

def display_current_games(streamer_name, games):
    user_games = list(games[games['user_name']==streamer_name]['game_name'])
    return user_games


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

def find_fuzzy_matches(input_token,comparison_list):
    '''
    Returns top 10 fuzzy matches and scores as tuples for one token in the comparison_list
    '''
    match_ratios = process.extract(input_token,comparison_list,limit=10)
    return match_ratios

def parse_user_list(user_input_list,unique_items_list):
    ''' Takes in tokens in comma separated list, then returns their most similar counterparts
    in the unique_items_list
    '''

    fuzzy_parsed = list()
    user_input_split = list(user_input_list.split(', '))
    for token in user_input_split:
        first_match = find_fuzzy_matches(token,unique_items_list)
        if first_match[0][1] > 70:
            fuzzy_parsed.append(find_fuzzy_matches(token,unique_items_list)[0][0])
    return fuzzy_parsed

def get_game_pic_urls(game_list):
    pic_url_list=list()
    with open( "static/models/pic_url_dict.pkl", "rb" ) as f:
        games = pickle.load(f)
    for item in game_list:
        pic_url_list.append(games[item])

    return pic_url_list

def make_prediction(streamer_name,streamer_genres,streamer_games):
    '''
    Given the name of a streamer, list of genres they enter, and a list of games they say
    they play, generate predictions based on similar genres and similar games to both
    what they enter into our website and what our database has recorded for them.
    '''
    genres, algo_genre_user, games, algo_game_user = load_models()

    streamer_genres = parse_user_list(streamer_genres, list(genres['game_genres'].unique()))
    streamer_games = parse_user_list(streamer_games, list(games['game_name'].unique()))

    print("FUZZY MATCHED STREAMER GAMES: ", streamer_games)
    print("FUZZY MATCHED STREAMER GENRES: ", streamer_genres)

    # Look at genres of games that the streamer is currently playing using our database
    recorder_genre_list = display_current_genres(streamer_name, genres)
    # Combine above with the genres the streamer has entered into our website
    full_genres = list(set(recorder_genre_list + streamer_genres))

    # Repeat above for games
    recorder_game_list = display_current_games(streamer_name, games)
    full_games = list(set(recorder_game_list + streamer_games))

    genre_iids = genres['game_genres'].unique()
    genre_iids_to_predict = np.setdiff1d(genre_iids, full_genres, assume_unique=True)

    # We are filling 'real' user rating of item to 4, but this does NOT have any effect on prediction

    genre_testset_personal = [[streamer_name, iid, 4.] for iid in genre_iids_to_predict]

    genre_personal_predictions = algo_genre_user.test(genre_testset_personal)
    genre_top_n = get_top_n(genre_personal_predictions)
    for uid, genre_user_ratings in genre_top_n.items():
        genre_user_based_list = [iid for (iid, _) in genre_user_ratings]

        #print("The recommended genres you're currently not streaming are:"+ str([iid for (iid, _) in user_ratings]))

    game_iids = games['game_name'].unique()
    game_iids_to_predict = np.setdiff1d(game_iids, full_games, assume_unique=True)
    game_testset_personal = [[streamer_name, iid, 4.] for iid in game_iids_to_predict]
    game_personal_predictions = algo_game_user.test(game_testset_personal)
    game_top_n = get_top_n(game_personal_predictions)
    for uid, game_user_ratings in game_top_n.items():
        game_user_based_list = [iid for (iid, _) in game_user_ratings]
        #print("The recommended games you're currently not streaming are:"+ str([iid for (iid, _) in user_ratings]))

    #Predicting Similar Genres/Games based on genre similarity to each other (item-based similarity)
    genre_group = pickle.load( open( "static/models/genre_group.pkl", "rb" ) )
    reader = Reader(rating_scale=(1, 5))
    genre_data = Dataset.load_from_df(genre_group[['user_name', 'game_genres', 'mean']], reader)
    genre_trainset = genre_data.build_full_trainset()

    game_group = pickle.load( open( "static/models/game_group.pkl", "rb" ) )
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
    print("Recommended genres: " + ', '.join(item for item in set(genres + genre_user_based_list)))
    print("Recommended games: " + ', '.join(item for item in set(games + game_user_based_list)))

    # combined outputs of both methods to produce results common in both
    genre_recommendations = set(genres + genre_user_based_list)
    game_recommendations = set(games + game_user_based_list)
    return_dict = dict()
    input_dict = dict()
    input_dict['streamer_name'] = streamer_name
    input_dict['streamer_genres'] = streamer_genres
    input_dict['streamer_games'] = streamer_games
    input_values = input_dict
    return_dict['genre_recommendations'] = genre_recommendations
    return_dict['game_recommendations'] = game_recommendations

    game_pic_urls = get_game_pic_urls(game_recommendations)
    game_pic_urls = [x.replace('-{width}x{height}','') for x in game_pic_urls]
    return input_values,return_dict, game_pic_urls[:5]

# For troubleshooting, pass some default parameters
if __name__ == '__main__':

    streamer_name = 'Ninja'
    streamer_genres = 'Action'
    streamer_games = 'Fortnite'


    input_values, recommendations, pic_urls = make_prediction(streamer_name,streamer_genres,streamer_games)
    print('Input Values: ',input_values['streamer_name'],
                            input_values['streamer_genres'],
                             input_values['streamer_games']  )

    print('Genres: ', recommendations['genre_recommendations'])
    print('Games: ', recommendations['game_recommendations'])
    print(pic_urls)
