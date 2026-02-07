"""
Test for Ollama client with mocked Prometheus metrics.
This test ensures the Ollama client works without requiring actual metrics infrastructure.
"""
import os
import sys
from unittest.mock import MagicMock, patch

# Add current directory to path
sys.path.append(os.getcwd())


def test_ollama_client_import():
    """Test that we can import the ollama client with mocked metrics."""
    # Mock the Prometheus metrics to avoid FileNotFoundError
    with patch('metrics.Counter') as mock_counter, \
         patch('metrics.Gauge') as mock_gauge, \
         patch('metrics.Histogram') as mock_histogram:

        # Configure mocks to return MagicMock instances
        mock_counter.return_value = MagicMock()
        mock_gauge.return_value = MagicMock()
        mock_histogram.return_value = MagicMock()

        # Now import should work
        from utils.ollama_client import chat_with_model

        # Verify import succeeded
        assert chat_with_model is not None
        print("✅ Ollama client imported successfully with mocked metrics")


def test_ollama_basic_functionality():
    """Test basic Ollama functionality with mocked dependencies."""
    with patch('metrics.Counter') as mock_counter, \
         patch('metrics.Gauge') as mock_gauge, \
         patch('metrics.Histogram') as mock_histogram, \
         patch('utils.ollama_client.requests.post') as mock_post:

        # Configure metric mocks
        mock_counter.return_value = MagicMock()
        mock_gauge.return_value = MagicMock()
        mock_histogram.return_value = MagicMock()

        # Configure requests mock
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'message': {'content': 'Hello! Yes, I am DeepSeek.'}
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        # Import and test
        from utils.ollama_client import chat_with_model

        response = chat_with_model(
            "deepseek-v3.1:671b-cloud",
            [("user", "Hello, are you DeepSeek?")],
            chat_id=999
        )

        # Verify response
        assert response is not None
        assert "DeepSeek" in response
        print(f"✅ Ollama client test passed: {response}")


if __name__ == "__main__":
    # Run tests when executed directly
    print("Running Ollama client tests...")
    test_ollama_client_import()
    test_ollama_basic_functionality()
    print("✅ All tests passed!")
