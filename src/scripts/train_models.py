import pandas as pd

from sopotek_trading_ai.models.model_manager import ModelManager
from sopotek_trading_ai.src.sopotek_trading_ai.quant.ml.training_pipeline import TrainingPipeline


def main():

    df = pd.read_csv("data/features/features.csv")

    pipeline = TrainingPipeline()

    X, y = pipeline.prepare(df)

    model_manager = ModelManager()

    model = model_manager.train(X, y)

    model_manager.save(model, "models/trained/model.pkl")

    print("Model training complete")


if __name__ == "__main__":
    main()