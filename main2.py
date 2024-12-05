from flask import Flask, request, jsonify
import google.generativeai as genai
import json
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

class CapabilityGenerator:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")

    def sanitize_response(self, response_text):
        """
        Sanitize the response text by removing unwanted elements like code fences.
        """
        sanitized = response_text.replace("```json", "").replace("```", "")
        return sanitized.strip()

    def generate_capabilities_chunk(self, industry: str, chunk_size=5):
        """
        Generate a smaller chunk of capabilities (e.g., 5 L0 capabilities).
        """
        prompt = f"""
        Generate 2 unique L0 capabilities for the {industry} industry. For each L0 capability, generate EXACTLY 20 unique L1 capabilities. For each L1 capability, GENER 20 unique L2 capabilities. Format the output as valid JSON.

        STRICTLY follow this format:
        {{
            "industry": "{industry}",
            "industry_description": "PROVIDE A BRIEF DESCRIPTION FOR THE {industry} INDUSTRY",
            "L0_capabilities": [
                {{
                    "L0_capability": "Name of an L0 capability",
                    "L0_capability_description": "Description of the L0 capability",
                    "L1_capabilities": [
                        {{
                            "L1_capability": "Name of an L1 capability",
                            "L1_capability_description": "Description of the L1 capability",
                            "L2_capabilities": [
                                {{
                                    "L2_capability": "Name of an L2 capability",
                                    "L2_capability_description": "Description of the L2 capability"
                                }}
                            ]
                        }}
                    ]
                }}
            ],
            "L0_capabilities_count": Number of L0 capabilities,
            "L1_capabilities_count": Number of L1 capabilities,
            "L2_capabilities_count": Number of L2 capabilities
        }}

        IMPORTANT: The output must be valid JSON with no comments, placeholders, or incomplete sections.
        """
        response = self.model.generate_content(prompt)
        return self.sanitize_response(response.text)

    def generate_level_2_capabilities(self, industry: str, level1_capabilities: list):
        """
        Generate a smaller chunk of level 2 capabilities (e.g., 5 L2 capabilities).
        """
        prompt = f"""
        Generate 20 unique L2 capabilities for the {industry} industry based on the previously generated L1 capabilities. Format the output as valid JSON.
        """
        
        response = self.model.generate_content(prompt)
        return self.sanitize_response(response.text)
        
    def merge_chunks(self, chunks):
        """
        Merge multiple chunks of L0 capabilities into a single JSON structure.
        """
        merged = []
        for chunk in chunks:
            merged.append(json.loads(chunk))
        return merged
    
    def merge_capabilities(self, chunks):
        """
        Merge multiple chunks of L0 capabilities into a single JSON structure.
        """
        merged = {"industry": "", "industry_description": "", "L0_capabilities": [], "L0_capabilities_count": 0, "L1_capabilities_count": 0, "L2_capabilities_count": 0}
        for chunk in chunks:
            try:
                chunk_json = json.loads(chunk)
                merged["industry"] = chunk_json["industry"]
                merged["industry_description"] = chunk_json["industry_description"]
                merged["L0_capabilities"].extend(chunk_json["L0_capabilities"])
                merged["L0_capabilities_count"] += chunk_json["L0_capabilities_count"]
                merged["L1_capabilities_count"] += chunk_json["L1_capabilities_count"]
                merged["L2_capabilities_count"] += chunk_json["L2_capabilities_count"]
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON received from the API")
        return merged

@app.route('/generate-capabilities', methods=['GET'])
def test_gemini():
    generator = CapabilityGenerator()
    industry = "Digital Commerce"

    # Generate capabilities in chunks
    chunks = []
    chunk = generator.generate_capabilities_chunk(industry, chunk_size=5)

    return chunk
    # Merge all chunks into a single JSON object
    
if __name__ == "__main__":
    app.run(debug=True)
