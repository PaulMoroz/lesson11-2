try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from infra import ecr_docker, ecs_service
