from twembeddings import build_matrix
from twembeddings import ClusteringAlgo, ClusteringAlgoSparse
from twembeddings import general_statistics, cluster_event_match, mcminn_eval

from sklearn.metrics.cluster import adjusted_mutual_info_score, adjusted_rand_score
import pandas as pd
import logging
import yaml
import argparse
import csv
# from sklearn.cluster import DBSCAN
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_distances
import numpy as np


logging.basicConfig(format='%(asctime)s - %(levelname)s : %(message)s', level=logging.INFO)
text_embeddings = ['tfidf_dataset', 'tfidf_all_tweets', 'w2v_gnews_en', "elmo", "bert", "sbert", "use"]
parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument('--model',
                    nargs='+',
                    required=True,
                    choices=text_embeddings,
                    help="""
                    One or several text embeddings
                    """
                    )
parser.add_argument('--dataset',
                    required=True,
                    help="""
                    Path to the dataset
                    """
                    )

parser.add_argument('--lang',
                    required=True,
                    choices=["en", "fr"])

parser.add_argument('--annotation',
                    required=False,
                    choices=["examined", "annotated", "no"])

parser.add_argument('--threshold',
                    nargs='+',
                    required=False
                    )

parser.add_argument('--batch_size',
                    required=False,
                    type=int
                    )

parser.add_argument('--remove_mentions',
                    action='store_true'
                    )

parser.add_argument('--window',
                    required=False,
                    default=24,
                    type=int
                    )
parser.add_argument('--sub-model',
                    required=False,
                    type=str
                    )

def main(args):
    with open("options.yaml", "r") as f:
        options = yaml.safe_load(f)
    for model in args["model"]:
        # load standard parameters
        params = options["standard"]
        logging.info("Clustering with {} model".format(model))
        if model in options:
            # change standard parameters for this specific model
            for opt in options[model]:
                params[opt] = options[model][opt]
        for arg in args:
            if args[arg] is not None:
                # params from command line overwrite options.yaml file
                params[arg] = args[arg]

        params["model"] = model
        test_params(**params)


def test_params(**params):
    # ADDED params daily and cluster_test : for now, you need to change locally for testing clustering by day
    daily = False
    cluster_test = False
    X, data = build_matrix(**params)
    params["window"] = int(data.groupby("date").size().mean()*params["window"]/24// params["batch_size"] * params["batch_size"])
    logging.info("window size: {}".format(params["window"]))
    params["distance"] = "cosine"
    # params["algo"] = "DBSCAN"
    # params["min_samples"] = 5
    thresholds = params.pop("threshold")
    for t in thresholds:
        logging.info("threshold: {}".format(t))
        logging.info("test cluster is {}".format(cluster_test))
        # clustering = DBSCAN(eps=t, metric=params["distance"], min_samples=params["min_samples"]).fit(X)        
        if params["model"].startswith("tfidf") and params["distance"] == "cosine":
            clustering = ClusteringAlgoSparse(threshold=float(t), window_size=params["window"],
                                              batch_size=params["batch_size"], intel_mkl=False)
            clustering.add_vectors(X)
        # added an if condition for testing cluster type
        if cluster_test :
            logging.info("trying test clustering")
            logging.info("successed to test clustering")
        else:
            clustering = ClusteringAlgo(threshold=float(t), window_size=params["window"],
                                        batch_size=params["batch_size"],
                                        distance=params["distance"])
            clustering.add_vectors(X)

        # ADDED an if condition for y_pred in cluster testing
        if cluster_test :
            logging.info("displaying clustering labels")
            y_pred = clustering.labels_ 
        else :
            y_pred = clustering.incremental_clustering()

        stats = general_statistics(y_pred)
        p, r, f1 = cluster_event_match(data, y_pred)
        ami = adjusted_mutual_info_score(data.label, y_pred)
        ari = adjusted_rand_score(data.label, y_pred)
        data["pred"] = data["pred"].astype(int)
        data["id"] = data["id"].astype(int)
        candidate_columns = ["date", "time", "label", "pred", "user_id_str", "id"]
        result_columns = []
        for rc in candidate_columns:
            if rc in data.columns:
                result_columns.append(rc)

        # MODIF ajout d'une condition if pour envoyer les résultats / jour dans un fichier dédié
        if cluster_test and daily:
            # MODIF : crée un fichier dédié à l'agglomerative clustering et les scores/jours avec les labels predits + les clusters pour chaque tweet.
            data[result_columns].to_csv(params["dataset"].replace(".", "_results_daily."),
                                        index=False,
                                        sep="\t",
                                        quoting=csv.QUOTE_NONE
                                        )
        else :
            data[result_columns].to_csv(params["dataset"].replace(".", "_results."),
                                        index=False,
                                        sep="\t",
                                        quoting=csv.QUOTE_NONE
                                        )
        try:
            mcp, mcr, mcf1 = mcminn_eval(data, y_pred)
        except ZeroDivisionError as error:
            logging.error(error)
            continue
        stats.update({"t": t, "p": p, "r": r, "f1": f1, "mcp": mcp, "mcr": mcr, "mcf1": mcf1, "ami": ami, "ari": ari})
        stats.update(params)
        stats = pd.DataFrame(stats, index=[0])

        # ADDED : date of the run when csv saves
        stats['datetime_of_run'] = pd.Timestamp.today().strftime('%Y-%m-%d-%H-%M')

        logging.info(stats[["t", "model", "tfidf_weights", "p", "r", "f1"]].iloc[0])
        if params["save_results"]:
            # ADDED update a scores/day file with new daily stats
            if cluster_test and daily:
            # commenter pour ne pas avoir un fichier historique de tous les runs AggloC
                # try:
                #     results = pd.read_csv("results_daily_cluster_tests.csv")
                # except FileNotFoundError:
                #     results = pd.DataFrame()
                # stats = pd.concat([results, stats], ignore_index=True)
                stats.to_csv("results_daily_cluster_tests.csv", index=False)
                logging.info("Saved results to results_daily_cluster_tests.csv")
            else :
                try:
                    results = pd.read_csv("results_clustering.csv")
                except FileNotFoundError:
                    results = pd.DataFrame()
                stats = pd.concat([results, stats], ignore_index=True)
                stats.to_csv("results_clustering.csv", index=False)
                logging.info("Saved results to results_clustering.csv")


if __name__ == '__main__':
    args = vars(parser.parse_args())
    main(args)