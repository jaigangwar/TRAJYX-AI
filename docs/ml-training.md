# TRAJYX risk model: data, training and evaluation

## What is implemented

The ML package now has one shared feature builder for training and inference,
a JSONL-to-CSV dataset builder, a deterministic segment-and-time holdout, an
XGBoost regressor, an evaluation command and an artifact loader for inference.
The model targets a reviewed 0–100 segment risk score. A model is not trained
or listed as accurate until a real labelled dataset exists and the evaluation
command has run successfully.

The existing weighted risk engine remains the live scoring source in the
meantime. Do not train on its output and call the result accuracy: that would
only teach the ML model to imitate the heuristic.

## Data required

Create an immutable dataset version (for example `junctions-reviewed-v1`) and
one JSONL record per road segment and time window. Each row must include the
segment definition, observed risk events, video-analysis summaries, UTC window
boundaries and a human-reviewed target score. Keep the source footage or
annotation reference in the dataset's private provenance manifest; do not put
faces, plates or direct identifiers in this training file.

Example record shape:

```json
{
  "dataset_version": "junctions-reviewed-v1",
  "segment": {
    "id": "junction-014",
    "path": [
      {"latitude": 28.6139, "longitude": 77.2090},
      {"latitude": 28.6144, "longitude": 77.2097}
    ],
    "lanes": 3,
    "speed_limit_kmh": 40,
    "one_way": false
  },
  "window_start": "2026-04-01T08:00:00Z",
  "window_end": "2026-04-01T09:00:00Z",
  "events": [],
  "analyses": [],
  "target_risk_score": 58
}
```

`events` and `analyses` are records from the TRAJYX domain schema. The target
must come from a documented human review or an independently observed outcome.
Use a label guide, at least two reviewers on an overlap sample, disagreement
resolution, and a record of the source/time window. Do not make labels by
copying `risk_score` from the current weighted engine. Synthetic demo records
must never enter an accuracy dataset.

Each dataset version needs at least five distinct segments and enough reviewed
windows to leave at least ten training and ten evaluation rows after the split.
The code will stop if it cannot produce that holdout; it will not silently
fall back to a random split.

## Run the workflow

From the repository root, with the project virtual environment activated:

```powershell
python -m pip install -r ml/requirements.txt
python -m pip install -e shared/python -e ml

python -m trajyx_ml.datasets.build `
  --input datasets/labels/junctions-reviewed-v1.jsonl `
  --dataset-version junctions-reviewed-v1 `
  --output datasets/processed/junctions-reviewed-v1.csv

python -m trajyx_ml.training.train `
  --dataset datasets/processed/junctions-reviewed-v1.csv `
  --output ml/artifacts/trajyx-risk-xgb/1.0.0

python -m trajyx_ml.evaluation.evaluate `
  --dataset datasets/processed/junctions-reviewed-v1.csv `
  --artifact ml/artifacts/trajyx-risk-xgb/1.0.0
```

The resulting folder contains `model.json`, `metadata.json`, and
`evaluation.json`. The split holds whole road segments out of training and
uses a later time window for evaluation. Dataset version, feature names,
hyperparameters, split sizes and cutoff are recorded beside the artifact.
Evaluation reports MAE, RMSE, R² when defined, macro precision/recall/F1 for
the four shared risk bands, and actual-versus-predicted calibration by band.

## Review before deployment

Read the evaluation file alongside the label protocol and split. Check sample
counts per band, calibration, errors by segment and time, detector coverage,
and the difference between the ML score and the explainable weighted score.
Compare against a simple baseline. A model with poor or unstable results
should not be deployed just because training completed. Never turn confidence,
training fit or simulation output into precision/recall.

`RiskPredictor` loads a versioned model and returns an explicit unavailable
state when there is no artifact. Production API registration and a
side-by-side prediction endpoint remain pending; until those are integrated,
the trained artifact is an offline research result and does not change live
driver alerts.

## What is still needed

- Real, permissioned CCTV/video or an appropriate public corpus, plus annotation
  time and an independent ground-truth protocol.
- Sufficient labelled time windows across multiple road segments and seasons.
- A reviewed evaluation run before any model accuracy appears in Model Health.
- A controlled endpoint/registry integration and deployment review after a
  model passes evaluation.
