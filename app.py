import streamlit as st
from io import BytesIO
import fitz  # PyMuPDF
import json
import re
from groq import Groq
from streamlit_pdf_viewer import pdf_viewer

# --------- PAGE CONFIGURATION ----------
st.set_page_config(page_title="Bank-Statement-extractor", page_icon="📖", layout="wide")

hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except Exception:
        pass

local_css("style.css")

# --------- ENHANCED PDF -> TEXT CONVERSION ----------
def convert_pdf_to_structured_text_advanced(pdf_file):
    """
    Enhanced PDF text extraction using PyMuPDF with better layout preservation
    and structural understanding for bank statements
    """
    if not pdf_file:
        return ""
    
    try:
        # Reset file pointer
        pdf_file.seek(0)
        pdf_bytes = pdf_file.read()
        
        # Open PDF with PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        structured_text = ""
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Method 1: Get text with layout preservation
            text_dict = page.get_text("dict")
            page_text = ""
            
            # Extract text blocks with better spacing
            blocks = page.get_text("blocks")
            for block in blocks:
                if len(block) >= 5 and isinstance(block[4], str):  # Text block
                    page_text += block[4] + "\n"
            
            # Alternative method for better structure preservation
            if not page_text.strip():
                page_text = page.get_text()
            
            # Clean up the text
            page_text = re.sub(r'\n\s*\n', '\n\n', page_text)  # Remove excess blank lines
            page_text = re.sub(r'[ \t]+', ' ', page_text)  # Normalize spaces
            
            structured_text += f"--- PAGE {page_num + 1} ---\n{page_text}\n\n"
        
        doc.close()
        return structured_text
        
    except Exception as e:
        st.error(f"Error processing PDF: {str(e)}")
        return ""

# --------- IMPROVED LLM PROMPTING ----------
def create_enhanced_prompt(structured_text):
    """
    Create a more structured prompt for better LLM extraction
    """
    return f"""You are an expert financial document analyzer. Extract the following information from this bank statement text.

EXTRACTION REQUIREMENTS:
- Bank name: The financial institution name
- Customer name: Account holder's full name  
- IBAN: International Bank Account Number (if available)
- Account number: Primary account identifier
- Phone number: Customer contact number
- Salary: Regular income/salary deposits (amount only)
- Statement balance: Current or closing balance
- Highest spent amount: Largest debit/withdrawal transaction
- Highest received amount: Largest credit/deposit transaction

OUTPUT FORMAT: Return ONLY a JSON array with exactly 9 values in this order:
[Bank name, Customer name, IBAN, Account number, Phone number, Salary, Statement balance, Highest spent amount, Highest received amount]

IMPORTANT RULES:
- Use "N/A" for any missing information
- Include only numerical values for amounts (no currency symbols)
- If this is not a bank statement, return: ["N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"]

BANK STATEMENT TEXT:
{structured_text}

JSON ARRAY:"""

# --------- ENHANCED DATA EXTRACTION ----------
def extract_bank_data_with_validation(structured_text, debug_mode=False):
    """
    Extract bank data with improved error handling and validation
    """
    try:
        # Enhanced prompt
        prompt = create_enhanced_prompt(structured_text)
        
        # Initialize Groq client
        client = Groq(api_key="")
        
        # Make API call with better parameters
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a precise financial document analyzer. Always return valid JSON arrays."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            temperature=0.1,  # Lower temperature for more consistent results
            max_tokens=1000
        )
        
        model_output = response.choices[0].message.content.strip()
        
        if debug_mode:
            st.markdown("#### Debug: Raw LLM Output")
            st.code(model_output)
        
        # Enhanced JSON extraction
        extracted_data = parse_llm_response(model_output, debug_mode)
        
        return extracted_data
        
    except Exception as e:
        st.error(f"Error during LLM processing: {str(e)}")
        return ["N/A"] * 9

def parse_llm_response(model_output, debug_mode=False):
    """
    Parse LLM response with multiple fallback methods
    """
    # Method 1: Direct JSON parsing
    try:
        # Look for JSON array pattern
        json_pattern = r'\[(?:[^[\]]*(?:\[[^\]]*\])?)*\]'
        matches = re.findall(json_pattern, model_output, re.DOTALL)
        
        for match in matches:
            try:
                arr = json.loads(match)
                if isinstance(arr, list) and len(arr) == 9:
                    return arr
            except json.JSONDecodeError:
                continue
    except Exception as e:
        if debug_mode:
            st.write(f"Debug: JSON parsing error: {e}")
    
    # Method 2: Extract from code blocks
    code_block_pattern = r'``````'
    code_matches = re.findall(code_block_pattern, model_output, re.DOTALL)
    
    for match in code_matches:
        try:
            arr = json.loads(match)
            if isinstance(arr, list) and len(arr) == 9:
                return arr
        except json.JSONDecodeError:
            continue
    
    # Method 3: Manual parsing as fallback
    try:
        # Look for quoted strings in array-like structure
        quoted_items = re.findall(r'"([^"]*)"', model_output)
        if len(quoted_items) >= 9:
            return quoted_items[:9]
    except Exception:
        pass
    
    # Return default if all methods fail
    if debug_mode:
        st.warning("Could not parse LLM response. Using default N/A values.")
    
    return ["N/A"] * 9

# --------- SIDEBAR: UPLOADER ----------
def clear_submit():
    st.session_state["submit"] = False

with st.sidebar:
    st.write("<p style='font-family: san serif; color: black; font-size: 20px;'>Upload PDF</p>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Upload file", type=["pdf"], on_change=clear_submit, label_visibility="hidden")
    
    # Processing options
    st.markdown("### Processing Options")
    debug_mode = st.checkbox("Show Debug Output")
    
    extracted_data = None
    
    if uploaded_file:
        with st.spinner("Processing PDF..."):
            # Use enhanced text extraction
            structured_text = convert_pdf_to_structured_text_advanced(uploaded_file)
            
            if structured_text.strip():
                # Extract data with improved method
                extracted_data = extract_bank_data_with_validation(structured_text, debug_mode)
                st.session_state["extracted_data"] = extracted_data
                
                if debug_mode:
                    st.markdown("#### Debug: Extracted Text Sample")
                    st.text_area("First 1000 characters:", structured_text[:1000], height=200)
                    
            else:
                st.warning("No text could be extracted from your PDF. Please try another PDF.")
                st.session_state["extracted_data"] = None
    else:
        st.session_state["extracted_data"] = None

# --------- MAIN LAYOUT ----------
col1, col2 = st.columns(spec=[2, 1], gap="small")

st.header("Enhanced Bank Statement Data Extractor")

if uploaded_file:
    with col1:
        with st.container(border=True):
            try:
                pdf_viewer(uploaded_file.getvalue())
            except Exception as e:
                st.error(f"Error displaying PDF: {e}")
    
    with col2:
        data = st.session_state.get("extracted_data", None)
        labels = [
            "Bank Name", "Customer Name", "IBAN", "Account Number",
            "Phone Number", "Salary", "Statement Balance",
            "Highest Debited", "Highest Credited"
        ]
        
        if data and isinstance(data, list) and len(data) == 9:
            with st.expander("💳 Customer Information", expanded=True):
                for i, (label, value) in enumerate(zip(labels, data)):
                    # Add icons for better visual appeal
                    icons = ["🏦", "👤", "🆔", "#️⃣", "📞", "💰", "💳", "📉", "📈"]
                    
                    col_a, col_b = st.columns([1, 2])
                    with col_a:
                        st.markdown(f"**{icons[i]} {label}:**")
                    with col_b:
                        # Style different types of data
                        if "amount" in label.lower() or "balance" in label.lower() or "salary" in label.lower():
                            if value != "N/A":
                                st.markdown(f"<span style='color: green; font-weight: bold;'>{value}</span>", unsafe_allow_html=True)
                            else:
                                st.write(value)
                        else:
                            st.write(value)
                    st.divider()
        else:
            st.error("❌ No information extracted or error occurred.")
            if debug_mode:
                st.write("Debug: Data structure issue")
                st.write(f"Data type: {type(data)}")
                st.write(f"Data content: {data}")

if not uploaded_file:
    st.markdown("""
    ## 🚀 Enhanced Bank Statement Analyzer
    
    This upgraded app uses **PyMuPDF** for superior text extraction and enhanced prompting techniques for better accuracy.
    
    ### ✨ New Features:
    - **Better Text Extraction**: Uses PyMuPDF (fitz) instead of PyPDF2 for improved accuracy
    - **Enhanced Layout Preservation**: Maintains document structure for better parsing
    - **Improved Error Handling**: Multiple fallback methods for data extraction
    - **Visual Enhancements**: Better UI with icons and formatted output
    - **Debug Mode**: Detailed logging for troubleshooting
    
    ### 📋 Extracted Information:
    - Bank name and customer details
    - Account numbers and IBAN
    - Contact information
    - Financial metrics (salary, balance, transactions)
    
    **Upload your bank statement PDF to get started!**
    """)
