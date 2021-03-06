from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# requirement 4.7

def test_getStrainGenesTrue():
    """
    check if the strain exist and returning all of th strain genes
    """
    response = client.get("/api/v1/cluster/get_gene_strain_id/GCF_000014625.1")
    assert response.status_code == 200
    assert len(response.json()) >= 6021


def test_getStrainGeneFalse():
    """
    check if the strain not exist
    """
    response = client.get("/api/v1/cluster/get_gene_strain_id/GCF_test")
    assert response.status_code == 400
    assert response.content == b'No Results'

