"""TRAJYX risk-modelling package.

    datasets/    dataset assembly and versioning
    features/    the feature contract shared by training and inference
    training/    training entry points and hyperparameter configuration
    evaluation/  metric computation and the model card written beside a model
    inference/   the serving wrapper the API calls

Two rules hold throughout:

1. Training and inference compute features through the *same* code path. A
   feature computed one way at training time and another at serving time is
   the most common source of a model that scores well offline and fails live.
2. No metric is ever written by hand. Every number the dashboard shows for a
   model comes from an evaluation run recorded in that model's metadata.
"""

__version__ = "0.1.0"
