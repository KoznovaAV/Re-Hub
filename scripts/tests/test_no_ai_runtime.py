"""P-07: prevent accidental reintroduction of the retired AI runtime."""
from pathlib import Path
import unittest
class NoAIRuntimeTest(unittest.TestCase):
    def test_no_ai_service_dependencies_or_route(self):
        root=Path(__file__).resolve().parents[2]
        files=['docker-compose.yml','deploy/docker-compose.prod.yml','.github/workflows/ci.yml','parser-service/requirements.txt','parser-service/requirements-import.txt']
        for file in files:
            text=(root/file).read_text().lower()
            for token in ['ai-service','ollama','transformers','torch','langchain','/ai/query']:
                with self.subTest(file=file,token=token):self.assertNotIn(token,text)
        for folder in ['backend/internal/api','frontend/src/views']:
            for file in (root/folder).glob('*'):
                if file.is_file():self.assertNotIn('/ai/query',file.read_text())
