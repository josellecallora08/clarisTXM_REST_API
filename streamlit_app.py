import streamlit as st
import google.generativeai as genai
import json
import os
import csv
import time
from io import StringIO
from dotenv import load_dotenv
import psutil

# Load environment variables
load_dotenv()

# Configure Gemini API using Streamlit secrets
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-1.5-flash")

# Utility Functions
def sanitize_response(response_text):
    """Sanitize Gemini response text."""
    return response_text.replace("```json", "").replace("```", "").strip()

def generate_capabilities_chunk(industry,chunks, chunk_size=2):
    """Generate L0 and L1 capabilities."""
    prompt = f"""
     Here are the L0 capabilities already generated: {chunks}
    Generate {chunk_size} unique L0 capabilities for the {industry} industry. Each L0 must have 20 unique L1 capabilities.
    
    1. Each L0 capability and its corresponding 20 L1 capabilities are distinct from each other.
    2. There should be no duplication of L0 or L1 capabilities within the entire output.
    3. Each L1 capability must be linked to only one L0 capability.
    
    Format the output strictly as valid JSON:
    {{
        "industry": "{industry}",
        "industry_description": "Provide a brief description of the {industry} industry.",
        "L0_capabilities": [
            {{
                "L0_capability": "Name",
                "L0_capability_description": "Description",
                "L1_capabilities": [
                    {{"L1_capability": "Name", "L1_capability_description": "Description"}}
                ]
            }}
        ]
    }}
    """
    response = model.generate_content(prompt)
    return json.loads(sanitize_response(response.text))

def generate_l2_capabilities(l1_capability):
    """Generate 20 L2 capabilities for an L1 capability."""
    prompt = f"""
    Generate exactly 20 unique L2 capabilities for the L1 capability: "{l1_capability['L1_capability']}".
    Format the output strictly as valid JSON:
    [
        {{
            "L2_capability": "Name",
            "L2_capability_description": "Description"
        }}
    ]
    """
    response = model.generate_content(prompt)
    return json.loads(sanitize_response(response.text))

def merge_l2_capabilities(complete_capabilities):
    """Add L2 capabilities to each L1 capability."""
    total_l1 = sum(len(l0["L1_capabilities"]) for l0 in complete_capabilities["L0_capabilities"])
    current = 0
    estimated_time_per_l1 = 2  # Estimate ~2 seconds per L1 capability
    total_estimated_time = total_l1 * estimated_time_per_l1
    start_time = time.time()

    progress_placeholder = st.empty()
    progress_bar = st.progress(0)
    
    for l0 in complete_capabilities["L0_capabilities"]:
        for l1 in l0["L1_capabilities"]:
            time.sleep(1)  # Simulate processing time
            l2_capabilities = generate_l2_capabilities(l1)
            l1["L2_capabilities"] = l2_capabilities
            current += 1
            progress_percent = (current / total_l1) * 100
            elapsed_time = time.time() - start_time
            remaining_time = total_estimated_time - elapsed_time
            progress_bar.progress(current / total_l1)
            progress_placeholder.text(f"Progress: {progress_percent:.2f}% - Estimated time remaining: {remaining_time:.2f} seconds")
    
    progress_bar.empty()
    progress_placeholder.empty()
    return complete_capabilities

def generate_csv(complete_capabilities):
    """Generate CSV content."""
    output = StringIO()
    csv_writer = csv.writer(output)
    headers = [
        "Industry", "Industry Description", "L0 Capability", 
        "L0 Capability Description", "L0 Capability Level", "L1 Capability", "L1 Capability Description",
        "L1 Capability Level", "L2 Capability", "L2 Capability Description", "L2 Capability Level"
    ]
    csv_writer.writerow(headers)
    
    for l0 in complete_capabilities["L0_capabilities"]:
        for l1 in l0["L1_capabilities"]:
            for l2 in l1.get("L2_capabilities", []):
                try:
                    # Validate structure of L2 capability
                    if isinstance(l2, dict) and "L2_capability" in l2 and "L2_capability_description" in l2:
                        csv_writer.writerow([
                            complete_capabilities["industry"],
                            complete_capabilities["industry_description"],
                            l0["L0_capability"], l0["L0_capability_description"], '0',
                            l1["L1_capability"], l1["L1_capability_description"], '1',
                            l2["L2_capability"], l2["L2_capability_description"], '2'
                        ])
                except Exception as e:
                    st.warning(f"Skipping invalid L2 capability: {l2}. Error: {str(e)}")
    return output.getvalue()

def log_memory_usage(step):
    """Log memory usage."""
    memory_usage = psutil.Process(os.getpid()).memory_info().rss / 1_048_576  # in MB
    st.write(f"Memory usage after {step}: {memory_usage:.2f} MB")

# Streamlit UI
st.title("AI Capability Generator 🌐")
st.write("Generate hierarchical capabilities (L0, L1, and L2) for any industry using Gemini AI.")

# User Input
industry = st.text_input("Enter Industry Name", placeholder="e.g., Healthcare, Finance, Retail")

# Generate Capabilities
if st.button("Generate Capabilities"):
    if not industry:
        st.error("Please provide a valid industry name.")
    else:
        st.info("Generating capabilities... Please wait.")
        start_time = time.time()
        
        # Memory log start
        log_memory_usage("Start")
        
        # Generate L0 and L1 capabilities
        chunks = []
        for _ in range(10):  # Two iterations for 2 L0 capabilities each
            try:
                chunk = generate_capabilities_chunk(industry,chunks, chunk_size=2)
                chunks.append(chunk)
            except Exception as e:
                st.error(f"Error during generation: {str(e)}")
                st.stop()
        
        # Merge capabilities
        complete_capabilities = {"industry": industry, "industry_description": "Generated description", "L0_capabilities": []}
        for chunk in chunks:
            complete_capabilities["L0_capabilities"].extend(chunk["L0_capabilities"])
        
        # Generate L2 Capabilities
        st.info("Generating L2 capabilities for all L1 capabilities...")
        complete_capabilities = merge_l2_capabilities(complete_capabilities)
        
        # Generate and Download CSV
        st.success("Capabilities generated successfully! Download your file below.")
        csv_data = generate_csv(complete_capabilities)
        st.download_button(
            label="Download Capabilities as CSV",
            data=csv_data,
            file_name="capabilities.csv",
            mime="text/csv"
        )
        
        # Memory log end
        log_memory_usage("End")
        
        # Display total time
        end_time = time.time()
        elapsed_time = end_time - start_time
        st.info(f"Process completed in {elapsed_time:.2f} seconds.")
