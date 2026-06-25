from pydantic import BaseModel


class RepositoryContext(BaseModel):
    affected_components: list[str] = []
    affected_services: list[str] = []
    affected_tests: list[str] = []
    architecture_constraints: list[str] = []
    risk_areas: list[str] = []
