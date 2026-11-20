from pydantic import BaseModel, Field


class SubmitKfragRequest(BaseModel):
    owner: str = Field(..., description="0x address of the data owner")
    provider: str = Field(..., description="0x address of the receiving provider")
    record_hash: str = Field(..., description="0x-prefixed keccak256 pointer to the record")
    kfrag_hex: str
    delegating_pk_hex: str = Field(..., description="owner's Umbral encryption public key")
    receiving_pk_hex: str = Field(..., description="provider's Umbral encryption public key")
    verifying_pk_hex: str = Field(..., description="owner's Umbral signing public key")
    # Owner authentication -- see auth.py.
    proxy_id: str = Field(..., description="PROXY_ID of the node this submission is addressed to")
    issued_at_ms: int = Field(..., description="unix epoch milliseconds at which the owner signed")
    owner_signature: str = Field(
        ..., description="owner's Ethereum (EIP-191) signature over the canonical submission message"
    )


class SubmitKfragResponse(BaseModel):
    stored: bool = True


class ReencryptRequest(BaseModel):
    owner: str
    provider: str
    record_hash: str
    capsule_hex: str


class ReencryptResponse(BaseModel):
    cfrag_hex: str


class HealthResponse(BaseModel):
    status: str
    proxy_id: str
    kfrags_held: int
    threshold: int
    shares: int
