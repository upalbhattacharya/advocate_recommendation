#!/home/workboots/VirtualEnvs/aiml/bin/python3
# -*- encoding: utf-8 -*-

# Birth: 2022-03-07 17:26:10.142410383 +0530
# Modify: 2022-03-14 13:45:16.508410941 +0530

"""Calculate precision, recall and mAP for queries."""

import argparse
import json
import os

import numpy as np

__author__ = "Upal Bhattacharya"
__license__ = ""
__copyright__ = ""
__version__ = "1.0"
__email__ = "upal.bhattacharya@gmail.com"


# For getting more information about numpy errors
np.seterr('raise')


def per_query_prec_rec(y_true, y_pred):
    """Takes a set of true values and their predictions and returns the
    precision and recall of each query .
    Shapes:
    y_true: (num_test, num_adv)
    y_pred: (num_test, num_adv)
    """
    # For storing the true and false positives and negatives of each class
    per_query_prec = []
    per_query_rec = []

    num_queries = y_true.shape[0]

    # Getting the positives and negatives of each class
    for query in range(num_queries):
        tp = np.dot(y_true[query, :], y_pred[query, :])
        pp = np.sum(y_pred[query, :])
        p = np.sum(y_true[query, :])

        prec = tp * 1./pp
        rec = tp * 1./p

        per_query_prec.append(prec)
        per_query_rec.append(rec)

    return per_query_prec, per_query_rec


def one_query_ap(precisions, y_true, relevance):
    """Computes the average precision of one query given the precision and
    relevance values."""
    return np.dot(
        precisions, relevance[:len(precisions)]) * 1./(np.sum(y_true))


def mAP(ap_values):
    """Computes the mean average precision from the per-class average precision
    values."""
    return np.mean(ap_values)


def convert_to_array(ordered_list, path):
    """Takes a list of files and a path and loads the data into a numpy
    array."""
    to_array = []
    for name in ordered_list:
        to_array.append(np.load(os.path.join(path,  name)))

    return np.stack(to_array, axis=0)


def vectorize_prediction(scores, adv_index, k):
    """Takes a set of documents, the ranking of their retrieval items and
    a k value and vectorizes them."""
    vectorized_list = []
    for case in list(scores.keys()):
        # Getting the top k elements
        ranked_list = scores[case][:k]
        vector = np.zeros(shape=(len(adv_index.keys()),))
        for ranked_item in ranked_list:
            vector[adv_index[ranked_item]] = 1
        vectorized_list.append(vector)

    return np.stack(vectorized_list, axis=0)


def relevance_at_k(scores, adv_index, y_true):
    vectorized_list = []
    for i, case in enumerate(list(scores.keys())):
        ranked_list = scores[case]
        vector = np.zeros(shape=(len(ranked_list),))
        for j, ranked_item in enumerate(ranked_list):
            if(y_true[i, adv_index[ranked_item]] == 1):
                vector[j] = 1
        vectorized_list.append(vector)

    return np.stack(vectorized_list, axis=0)


def numpy_to_dict(array, cases, metric='P'):
    """Converts a numpy of precision or recall values into a dict"""
    numpy_dict = {}
    for i, case in enumerate(cases):
        numpy_dict[case] = {f"{metric}@{j+1}": value for j,
                            value in enumerate(array[i, :])}

    return numpy_dict


def create_targets(targets_dict, adv_index, cases,
                   case_charges=None, adv_charges=None, threshold=None):
    """Create targets from a dictionary of targets and advocate ordering.

    Parameters
    ----------

    targets_dict : dict
        Dictionary with the targets of each case.
    adv_list : list
        List of advocates to consider.
    cases : list
        Ordered list cases.

    Returns
    -------
    result : numpy.array
        Stacked target mult-hot vectors.
    """
    actual = []
    lenient = []
    for case in cases:
        # mAP lenient
        l = [0 for _ in range(len(adv_index.keys()))]
        if all(ele is not None
               for ele in [case_charges, adv_charges, threshold]):
            l = np.array([int(adv not in targets_dict[case] and
                              len(set(adv_charges[adv]).intersection(
                                  set(case_charges[case]))) * 1./len(
                                      case_charges[case]) >= threshold)
                          for adv in list(adv_index.keys())],
                         dtype=np.float32)
        # mAP hard
        a = np.array([int(adv in targets_dict[case])
                      for adv in list(adv_index.keys())],
                     dtype=np.float32)

        actual.append(a)
        lenient.append(l)

    return np.stack(actual, axis=0), np.stack(lenient, axis=0)


def at_k_values(prec: list[float], rec: list[float]) -> dict:

    values = {
            "prec": sum(prec) * 1./len(prec),
            "rec": sum(rec) * 1./len(rec)
            }
    return values


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--scores_path",
                        help="Path to load scores from. Metrics go back here.")
    parser.add_argument("-t", "--case_targets_path",
                        help="Path to load the case targets from.")
    parser.add_argument("-k", "--top_k", type=int, default=10,
                        help="Top k values to consider for computation.")
    parser.add_argument("-a", "--at_k", nargs="+", type=int,
                        default=[5, 10, 15, 20, 25],
                        help=("k values at which to compute macro precision "
                              "and recall."))
    parser.add_argument("-c", "--case_charges_path", default=None,
                        help="Path to case charges.")
    parser.add_argument("-ac", "--advocate_charges_path", default=None,
                        help="Path to advocate charges.")
    parser.add_argument("-th", "--threshold", default=None, type=float,
                        help="Threshold when using mAP lenient.")
    parser.add_argument("-n", "--name",
                        help="Name of mAP strategy.")

    args = parser.parse_args()

    with open(args.scores_path, 'r') as f:
        scores = json.load(f)

    output_path, _ = os.path.split(args.scores_path)
    output_path = os.path.join(output_path, args.name)
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    adv_list = list(scores[list(scores.keys())[0]].keys())

    adv_index = {k: i for i, k in enumerate(sorted(adv_list))}

    with open(args.case_targets_path, 'r') as f:
        targets = json.load(f)

    # Load extra data for mAP lenient
    case_charges = None
    adv_charges = None
    threshold = None
    if all([ele is not None for ele in [args.case_charges_path,
                                        args.advocate_charges_path,
                                        args.threshold]]):
        with open(args.case_charges_path, 'r') as f:
            case_charges = json.load(f)

        with open(args.advocate_charges_path, 'r') as f:
            adv_charges = json.load(f)
        threshold = args.threshold

    # Creating the array to actual targets
    array_actual, array_lenient = create_targets(
                                                targets, adv_index,
                                                list(scores.keys()),
                                                case_charges=case_charges,
                                                adv_charges=adv_charges,
                                                threshold=threshold)
    array_actual_lenient = array_actual + array_lenient

    # Ordering the scores for each advocate
    scores = {case_id: [adv for adv, score in sorted(pred.items(),
                                                     key=lambda x: x[1],
                                                     reverse=True)] for
              case_id, pred in scores.items()}

    # Top K
    top_k = np.arange(start=1, stop=args.top_k + 1)

    # For storing the precision and recall scores across different thresholds
    precision_scores = []
    recall_scores = []

    ap_scores = []
    ap_dict = {}
    at_k = {}

    for k in top_k:
        array_pred = vectorize_prediction(scores, adv_index, k)

        # For each query
        prec, rec = per_query_prec_rec(array_actual_lenient,
                                       array_pred)

        # For precision@k and recall@k

        if k in args.at_k:
            at_k[int(k)] = at_k_values(prec, rec)

        precision_scores.append(prec)
        recall_scores.append(rec)

    # Computing relevance for AP calculation
    relevance = relevance_at_k(scores, adv_index, array_actual_lenient)

    # Stacking along first axis Shape = (top_k, num_queries)
    precision_scores = np.stack(precision_scores, axis=0)
    recall_scores = np.stack(recall_scores, axis=0)

    # Shape = (num_queries, top_k)
    precision_scores = precision_scores.T
    recall_scores = recall_scores.T

    # Calculating the AP scores for each query
    for query, case_id in enumerate(list(scores.keys())):
        ap = one_query_ap(precision_scores[query, :],
                          array_actual_lenient[query, :],
                          relevance[query, :])

        ap_dict[case_id] = ap
        ap_scores.append(ap)

    # Calculating the query mAP
    mean_ap = mAP(ap_scores)

    # Sorting the AP scores in descending order
    ap_dict = {k: v for k, v in sorted(ap_dict.items(), key=lambda x:
                                       x[1], reverse=True)}

    # Converting to a dictionary for human readability
    prec_dict = numpy_to_dict(precision_scores, list(scores.keys()), 'P')
    rec_dict = numpy_to_dict(recall_scores, list(scores.keys()), 'R')

    # Saving all the generated data
    with open(os.path.join(output_path, "per_query_precision.json"),
              'w+') as f:
        json.dump(prec_dict, f, indent=4)

    with open(os.path.join(output_path, "per_query_recall.json"),
              'w+') as f:
        json.dump(rec_dict, f, indent=4)

    with open(os.path.join(output_path, "per_query_ap.json"),
              'w+') as f:
        json.dump(ap_dict, f, indent=4)

    with open(os.path.join(output_path, "prec_rec_at_k.json"),
              'w+') as f:
        json.dump(at_k, f, indent=4)

    with open(os.path.join(output_path, "mAP.txt"),
              'w+') as f:
        f.write(str(mean_ap))

    np.save(os.path.join(output_path, "top_k"), top_k)
    np.save(os.path.join(output_path, "precision"), precision_scores)
    np.save(os.path.join(output_path, "recall"), recall_scores)
    np.save(os.path.join(output_path, "ap"), ap_scores)


if __name__ == '__main__':
    main()
