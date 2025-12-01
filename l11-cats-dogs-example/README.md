### Instalation
```zsh
uv sync
```

### Setup
- Copy model to models/model.pth
- Setup DVC
```zsh
dvc init
dvc remote add -d storage s3://dvcstore-my-storage/shared
dvc add models/model.pth
git add models/model.pth.dvc
dvc push models/model.pth.dvc
```

- Apply ci-cd-iam-policy.json to the CI/CD bot

### Run
```
streamlit run src/l11_cats_dogs/main.py
```

### Deploy
Create the ECS cluster "dev-cluster" on AWS
```
pulumi login s3://my-pulumi-bucket
pulumi stack select cats-dogs.dev
pulumi up
```

### REMOVE ALL RESOURCE AFTER USAGE
```
pulumi destroy
```
