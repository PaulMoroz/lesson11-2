import base64
import json
import os

import pulumi
import pulumi_aws as aws
import pulumi_docker as docker
from pulumi import StackReference

region = aws.config.region

stack = pulumi.get_stack()
project, env = stack.split(".", maxsplit=1)
prefix = stack.replace(".", "-")

config = pulumi.Config()
docker_build_context = config.require("docker_build_context")
dockerfile = config.require("dockerfile")
docker_platform = config.require("docker_platform")
cpu_architecture = config.require("cpu_architecture")
docker_tag = config.require("docker_tag")

ecr_repo = aws.ecr.Repository(
    f"{prefix}-ecr-repo",
    image_scanning_configuration=aws.ecr.RepositoryImageScanningConfigurationArgs(
        scan_on_push=False,
    ),
    image_tag_mutability="MUTABLE",
    force_delete=True,
)


def get_registry_info(rid: str) -> docker.RegistryArgs:
    creds = aws.ecr.get_authorization_token(registry_id=rid)
    decoded = base64.b64decode(creds.authorization_token).decode()
    username, password = decoded.split(":", 1)
    return docker.RegistryArgs(
        server=creds.proxy_endpoint, username=username, password=password
    )


docker_registry = ecr_repo.registry_id.apply(get_registry_info)

docker_image = docker.Image(
    f"{prefix}-docker-image",
    build=docker.DockerBuildArgs(
        context=docker_build_context,
        dockerfile=dockerfile,
        platform=docker_platform,
        cache_from=docker.CacheFromArgs(
            images=[ecr_repo.repository_url.apply(lambda url: f"{url}:latest")]
        ),
    ),
    image_name=ecr_repo.repository_url.apply(lambda v: f"{v}:{docker_tag}"),
    skip_push=False,
    registry=docker_registry,
)

pulumi.export(f"{prefix}-docker-image", docker_image.image_name)
pulumi.export(f"{prefix}-docker-image-repo-digest", docker_image.repo_digest)
pulumi.export(f"{prefix}-ecr-repo-url", ecr_repo.repository_url)
