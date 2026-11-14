from app.contracts.workers import ArtifactMetadata


class ArtifactCatalog:
    """Small metadata registry; never downloads or interprets raster arrays.

    Callers supply stable artifact/version IDs and full provenance. Registration
    is not proof that geometry/CRS/data quality have been independently verified.
    """

    def __init__(self):
        self._metadata: dict[str, ArtifactMetadata] = {}

    def register(self, metadata: ArtifactMetadata) -> None:
        checked = ArtifactMetadata.model_validate(metadata.model_dump())
        if checked.artifact_id in self._metadata:
            raise ValueError("Artifact ID already registered; use a new processing version ID.")
        self._metadata[checked.artifact_id] = checked.model_copy(deep=True)

    def get(self, artifact_id: str) -> ArtifactMetadata | None:
        metadata = self._metadata.get(artifact_id)
        return metadata.model_copy(deep=True) if metadata else None
