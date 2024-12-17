import psutil


import csv
from flask import Flask, request, jsonify, Response, stream_with_context
import google.generativeai as genai
import json
import os
from io import StringIO
from dotenv import load_dotenv
import groq

load_dotenv()

app = Flask(__name__)

class CapabilityGenerator:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.groq_client = groq.Groq(api_key=self.groq_api_key)
        
    def sanitize_response(self, response_text):
        """
        Sanitize the response text by removing unwanted elements like code fences.
        """
        return response_text.replace("```json", "").replace("```", "").strip()

    def generate_capabilities_chunk(self, industry: str, chunks: list, chunk_size=5):
        """
        Generate  a smaller chunk of capabilities (e.g., 5 L0 capabilities).
        """
        prompt = f"""
        Here are the L0 capabilities already generated: {chunks}
Generate {chunk_size} distinct L0 capabilities for the {industry} industry. Each L0 capability should have exactly 20 unique L1 capabilities. Ensure that:

1. Each L0 capability and its corresponding 20 L1 capabilities are distinct from each other.
2. There should be no duplication of L0 or L1 capabilities within the entire output.
3. Each L1 capability must be linked to only one L0 capability.

Output the result as valid JSON in the following format:

{{
    "industry": "{industry}",
    "industry_description": "Provide a brief, high-level description of the {industry} industry.",
    "L0_capabilities": [
        {{
            "L0_capability": "Name of a unique L0 capability in the {industry} industry",
            "L0_capability_description": "Provide a detailed, unique description for the L0 capability",
            "L1_capabilities": [
                {{
                    "L1_capability": "Name of a unique L1 capability for the L0 capability",
                    "L1_capability_description": "Provide a detailed description for each L1 capability"
                }},
                ...
                (exactly 20 distinct L1 capabilities)
            ]
        }},
        ...
        (up to {chunk_size} L0 capabilities)
    ],
    "L0_capabilities_count": {chunk_size},
    "L1_capabilities_count": {chunk_size * 20},
    "L2_capabilities_count": 0
}}

Ensure that the JSON output is strictly valid, with no placeholders or comments. The L0 and L1 capabilities should be creative, relevant, and varied across different facets of the {industry} industry. Avoid repeating any capability names or descriptions across all L0 and L1 capabilities.
"""

        try:
            response = self.model.generate_content(prompt)
            return json.loads(self.sanitize_response(response.text))
        except Exception as e:
            raise RuntimeError("API exhausted or an error occurred while generating content") from e
        
    def stream_csv(self, complete_capabilities):
        """
        Stream CSV data to save memory.
        """
        def generate_rows():
            headers = [
                "Industry", "Industry Description", "L0 Capability",
                "L0 Capability Description", "L0 Level",
                "L1 Capability", "L1 Capability Description", "L1 Level"
            ]
            yield ','.join(headers) + '\n'
            
            for l0 in complete_capabilities["L0_capabilities"]:
                for l1 in l0["L1_capabilities"]:
                    row = [
                        complete_capabilities["industry"],
                        "Industry Description",
                        l0["L0_capability"],
                        l0["L0_capability_description"], "0",
                        l1["L1_capability"],
                        l1["L1_capability_description"], "1"
                    ]
                    yield ','.join(row) + '\n'
                    
        return stream_with_context(generate_rows())
    
    def generate_l2_capabilities(self, l1_capabilities):
        """
        Purpose: Generate L2 capabilities for a given L1 capability.
        """
        
        prompt = f"""
            Based on the following L1 capabilities: {l1_capabilities}, generate EXACTLY 20 DISTINCT L2 capabilities for each L1 capability. Ensure that the L2 capabilities are relevant to the provided L1 capabilities. Format the output as a JSON array containing only the L2 capabilities.

            STRICTLY adhere to the following requirements:
            1. The output must be a JSON array containing objects for each L2 capability.
            2. Each object in the array should have the following format, DO NOT PUT IT IN AN ARRAY OR IN []:
            {{
                "L2_capability": "Name of an L2 capability",
                "L2_capability_description": "Description of the L2 capability"
            }}
            3. Ensure there are STRICTLY AND EXACTLY 20 unique L2 capabilities for each L1 capability provided {l1_capabilities}, with unique names and meaningful descriptions.
            4. Validate the output to ensure it is valid JSON format. Avoid trailing commas or missing closures.
            5. Double-check the output for formatting and logical consistency before returning.
        """

        try:
            level_two_capabilties = self.model.generate_content(prompt)
            print(level_two_capabilties.text)
            return self.sanitize_response(level_two_capabilties.text)
        except Exception as e:
            raise RuntimeError("API exhausted or an error occurred while generating content") from e
        
    # end def
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

    def merge_l2_capabilities(self, l1_capabilities):
        """
        Merge multiple chunks of L2 capabilities into a single JSON structure.
        Ensure there are STRICTLY AND EXACTLY 20 L2 capabilities for each L1 capability provided.
        """
        # merged = {}
        # for l1 in l1_capabilities:
        #     merged[l1["L1_capability"]] = l1["L2_capabilities"]
        # return merged
        return l1_capabilities
    
    def merge_l1_to_l2(self, l1_capabilities, l2_capabilities):
        """
        Merge L1 capabilities and L2 capabilities into a single JSON structure.
        """
        
        for l0_item in l1_capabilities["L0_capabilities"]:
            for l1_item in l0_item["L1_capabilities"]:
                # Look for a match in the L2_capabilities
                for l2_item in l2_capabilities:
                    if l2_item["L1_capability"] == l1_item["L1_capability"] and l2_item["L1_capability_description"] == l1_item["L1_capability_description"]:
                        # Append L2_capabilities to the L1_item
                        l1_item["L2_capabilities"] = l2_item["L2_capabilities"]
        return l1_capabilities  # Return if no match is found

    def generate_csv(self, complete_capabilities):
        """
        Generate a CSV file based on the completed final JSON structure.
        """
        rows = []

        for l0_item in complete_capabilities["L0_capabilities"]:
            industry = complete_capabilities["industry"]
            industry_description = complete_capabilities["industry_description"]
            
            # Iterate over L1 capabilities
            for l1_item in l0_item["L1_capabilities"]:
                l0_capability = l0_item["L0_capability"]
                l0_capability_description = l0_item["L0_capability_description"]
                
                # Iterate over L2 capabilities
                for l2_item in l1_item.get("L2_capabilities", []):
                    l1_capability = l1_item["L1_capability"]
                    l1_capability_description = l1_item["L1_capability_description"]
                    l2_capability = l2_item["L2_capability"]
                    l2_capability_description = l2_item["L2_capability_description"]
                    
                    # Append each row to the list
                    rows.append([
                        industry, 
                        industry_description, 
                        l0_capability, 
                        l0_capability_description, 
                        "0",  # This can be static for L0
                        l1_capability, 
                        l1_capability_description, 
                        "1",  # This can be static for L1
                        l2_capability, 
                        l2_capability_description, 
                        "2"   # This can be static for L2
                    ])

        # Create a CSV file from the rows list
        output = StringIO()
        csv_writer = csv.writer(output)
        
        # Writing headers to CSV
        headers = [
            "Industry", "Industry Description", "L0 Capability", 
            "L0 Capability Description", "L0 Capability Level",
            "L1 Capability", "L1 Capability Description", "L1 Capability Level",
            "L2 Capability", "L2 Capability Description", "L2 Capability Level"
        ]
        csv_writer.writerow(headers)
        
        # Write all data rows
        csv_writer.writerows(rows)
        
        # Get CSV content
        output.seek(0)
        return output.getvalue()    

    def log_memory_usage(self, step):
        memory_usage = psutil.Process(os.getpid()).memory_info().rss / 1_048_576  # in MB
        print(f"Memory usage after {step}: {memory_usage} MB")
    
@app.route('/generate-capabilities', methods=['GET'])
def test_gemini():
    generator = CapabilityGenerator()
    print(request.args.get('industry'))
    industry = request.args.get('industry')
    generator.log_memory_usage("start")
    # Generate capabilities in chunks
    chunks = []
    for _ in range(1):  # 4 chunks of 5 L0 capabilities = 20 total
        try:
            chunk = generator.generate_capabilities_chunk(industry, chunks, chunk_size=2)
            chunks.append(chunk)
        except RuntimeError as e:
            return jsonify({"error": "API exhausted or failed to generate capabilities", "details": str(e)}), 500

    # Merge all chunks into a single JSON object
    try:
        complete_capabilities = generator.merge_capabilities(chunks)
    except ValueError as e:
        return jsonify({"error": "Failed to merge capabilities", "details": str(e)}), 500
    generator.log_memory_usage("merge_capabilities")
    # This will return a JSON response containing the L1 capabilities of all L0 capabilities 
    # from the complete capabilities generated. It extracts the L1 capabilities from the 
    # complete_capabilities dictionary and formats them as a JSON response.
    all_l1_capabilities = []
    for l0 in complete_capabilities["L0_capabilities"]:
        all_l1_capabilities.extend(l0["L1_capabilities"])
    generator.log_memory_usage("generate_l2_capabilities")
    # l2_capabilities = generator.generate_l2_capabilities(all_l1_capabilities)
    l0_count = len(all_l1_capabilities)
    print(f"L0 count: {l0_count}")
    
    l2_chunks = []
    # This will return a JSON response containing the L2 capabilities of the first L1 capability 
    for index, l1 in enumerate(all_l1_capabilities):  # Use enumerate to get index
        l2_capabilities = generator.generate_l2_capabilities(l1)
        res = json.loads(l2_capabilities)
        print(res)
        
        transformed_item = {
            "L1_capability": l1["L1_capability"],
            "L1_capability_description": l1["L1_capability_description"],
            "L2_capabilities": res
        }
        print(f'Generation of L2: {index}')  # This will print the index of the current L1 capability being processed
        final_l2_chunks = transformed_item
        l2_chunks.append(final_l2_chunks)
    
    generator.log_memory_usage("merge_l1_to_l2")
    generator.merge_l1_to_l2(complete_capabilities, l2_chunks)
    generator.log_memory_usage("generate_csv")
    csv_content = generator.generate_csv(complete_capabilities)
    generator.log_memory_usage("generate_csv")
    response = Response(csv_content, mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=capabilities.csv"
    generator.log_memory_usage("end")
    return response


@app.route('/capabilities', methods=['GET'])  
def sample():
    """
    Purpose:
    """
    this = CapabilityGenerator()
    industry = request.args.get('industry')
   
    prompt = f"""
    You are an expert in the field of capabilities for the {industry} industry.
    
    Generate 5 unique L0 capabilities for the {industry} industry. For each L0 capability, generate EXACTLY 20 unique L1 capabilities and L1 Descriptions. For Each L1 capability, generate EXACTLY 20 unique L2 capabilities and L2 Descriptions. Format the output as a JSON object that matches the INDUSTRIES_LEVEL_0 structure.
    
    Please strictly follow the format and structure of the INDUSTRIES_LEVEL_0 JSON object.
    CAPABILITIES_LEVEL_0 = {{
        "l0_capability": "",
        "l0_capability_description": "",
        "l1_capabilities": list[CAPABILITIES_LEVEL_1]
    }}
    CAPABILITIES_LEVEL_1 = {{
        "l1_capability": "",
        "l1_capability_description": "",
        "l2_capabilities": list[CAPABILITIES_LEVEL_2]
    }}
    CAPABILITIES_LEVEL_2 = {{
        "l2_capability": "",
        "l2_capability_description": ""
    }}
    
    {{
        "INDUSTRIES": {{
            "industry": "{industry}",
            "industry_description": "",
            "L0_capabilities": list[CAPABILITIES_LEVEL_0],
            "L0_capabilities_count": 0,
            "L1_capabilities_count": 0,
            "L2_capabilities_count": 0
        }}
    }}
    """ 
    

    generatedcontent = this.model.generate_content(prompt)
    print(generatedcontent.text)
    
    generate_l2_capabilities = this.model.generate_content("""

                                                           
                                                           """)
    

# end def
if __name__ == "__main__":
    app.run(debug=True)
