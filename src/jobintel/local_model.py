"""The single supported CPU model and engine, pinned by content rather than tags."""

ENGINE_IMAGE = "ghcr.io/ggml-org/llama.cpp@sha256:bf3da52e92c083472b3d1c9f9da081f423ab9def95a87ec4bba51940382d75fd"
ENGINE_REVISION = "f2918cabbffe8abf8e2a90c1c089085fa116c2cf"
MODEL = "jobintel-qwen2.5-1.5b-f16"
MODEL_FILE = "qwen2.5-1.5b-instruct-f16.gguf"
MODEL_SHA256 = "b6eaec3509f1d0373d1f4802654c4a7bfcde0768645d2d45e8885f6922b428ee"
MODEL_BYTES = 3093669376
MODEL_MANIFEST = "sha256:b83c287163f67ba50ebebd583ae0f02fa3f9a8ebe5d4596c6d367460a75d88e6"
MODEL_REPOSITORY = "ai/qwen2.5"
LICENSE_SHA256 = "609e2cb599f84aaa41d8ef29d8fdb04d164fab22e8d9292ca34a599d0f56a338"
LICENSE_BYTES = 12624


def model_identity():
    return {
        "engine": "llama.cpp",
        "engine_revision": ENGINE_REVISION,
        "engine_image": ENGINE_IMAGE,
        "model_repository": MODEL_REPOSITORY,
        "model_revision": MODEL_MANIFEST,
        "model_weights_sha256": MODEL_SHA256,
        "model_license": "Apache-2.0",
    }
