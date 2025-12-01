from pathlib import Path
from typing import Final

import numpy as np
import streamlit as st
import torch
from PIL import Image
from torchvision import transforms

from l11_cats_dogs.model_arch import ImageClassifier

MODEL_PATH: Final = Path("models/model.pth")
DEFAULT_IMAGE_SIZE: Final = (224, 224)
CLASS_NAMES: Final = ("cat", "dog")
SEED: Final = 42

DEVICE: Final = torch.device("cuda" if torch.cuda.is_available() else "cpu")

torch.manual_seed(SEED)
np.random.seed(SEED)


@st.cache_resource(show_spinner=False)
def load_model(model_path: Path) -> torch.nn.Module:
    model = ImageClassifier()
    model.load_state_dict(torch.load(model_path, map_location=DEVICE))
    model.to(DEVICE)
    model.eval()
    return model


@st.cache_resource(show_spinner=False)
def build_transform(image_size: tuple[int, int]) -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.Resize(image_size),
            transforms.ToTensor(),
        ]
    )


def preprocess(image: Image.Image, transform: transforms.Compose) -> torch.Tensor:
    if image.mode != "RGB":
        image = image.convert("RGB")
    tensor = transform(image).unsqueeze(0)
    return tensor


def predict(image_tensor: torch.Tensor, model: torch.nn.Module) -> torch.Tensor:
    with torch.inference_mode():
        logits = model(image_tensor)
        probabilities = torch.softmax(logits, dim=1)
    return probabilities.squeeze(0)


def format_probabilities(probabilities: torch.Tensor) -> list[tuple[str, float]]:
    pairs: list[tuple[str, float]] = []
    for idx, score in enumerate(probabilities):
        label = CLASS_NAMES[idx] if idx < len(CLASS_NAMES) else f"class_{idx}"
        pairs.append((label, float(score)))
    return pairs


def render_prediction(probabilities: list[tuple[str, float]]) -> None:
    st.subheader("Prediction")
    for label, score in probabilities:
        st.write(f"{label}: {score:.2%}")
        st.progress(score)


def main() -> None:
    st.set_page_config(page_title="Cats vs Dogs", page_icon="🐾", layout="centered")
    st.title("Cats vs Dogs Classifier")
    st.caption(
        "Upload an image to classify it as a cat or a dog using a PyTorch model."
    )

    if not MODEL_PATH.exists():
        st.error(f"Model file not found at {MODEL_PATH}.")
        return

    model = load_model(MODEL_PATH)
    transform = build_transform(DEFAULT_IMAGE_SIZE)

    uploaded_file = st.file_uploader("Choose an image", type=["png", "jpg", "jpeg"])
    if uploaded_file is None:
        return

    image = Image.open(uploaded_file)
    st.image(image, caption="Uploaded image", width="stretch")

    image_tensor = preprocess(image, transform)
    probabilities_tensor = predict(image_tensor, model)
    probability_pairs = format_probabilities(probabilities_tensor)
    render_prediction(probability_pairs)


if __name__ == "__main__":
    main()
