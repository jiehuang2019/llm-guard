from huggingface_hub import snapshot_download
snapshot_download("dslim/bert-base-NER", local_dir="./models/dslim__bert-base-NER", local_dir_use_symlinks=False)
snapshot_download("microsoft/deberta-v3-large-mnli", local_dir="./models/deberta-v3-large-mnli", local_dir_use_symlinks=False)
snapshot_download("unitary/unbiased-toxic-roberta", local_dir="./models/unbiased-toxic-roberta", local_dir_use_symlinks=False)  # or detoxify large

