
from flask import Flask, render_template, request, jsonify, send_file
import pdfplumber
import os
import json
from datetime import datetime
import base64

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

app = Flask(__name__)

# Ensure templates folder exists
if not os.path.exists('templates'):
    os.makedirs('templates')

# Ensure uploads folder exists
if not os.path.exists('uploads'):
    os.makedirs('uploads')

@app.route('/')
def index():
    return render_template('index1.html')

@app.route('/upload', methods=['POST'])
def upload_pdf():
    if 'pdfFile' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['pdfFile']

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file and file.filename.lower().endswith('.pdf'):
        # Save the uploaded file temporarily
        filename = f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        filepath = os.path.join('uploads', filename)
        file.save(filepath)
        
        # Add this line to store original filename
        original_filename = os.path.splitext(file.filename)[0]  # Remove .pdf extension
        
        # Convert PDF to base64 for display
        with open(filepath, 'rb') as f:
            pdf_data = base64.b64encode(f.read()).decode('utf-8')
        
        return jsonify({
        "success": True,
        "filename": filename,
        "original_filename": original_filename,  # Add this line
        "pdf_data": pdf_data,
        "message": "PDF uploaded successfully. Please review and click Submit to extract data."
        })
    
    return jsonify({"error": "Please upload a valid PDF file"}), 400


def send_mail(data, file_path):
    try:
        message = MIMEMultipart()
        sender_email = 'mayurnandanwar@ghcl.co.in'
        message["From"] = sender_email
        receiver_email = 'amitahiniya@ghcl.co.in' 
        message["To"] = receiver_email
        message["Subject"] = "Extracted Information"
        
        json_string = json.dumps(data, indent=4)
        body = "Extracted_Information: \n"+str(json_string)
        message.attach(MIMEText(body, "plain"))
        
        with open(file_path, "rb") as file:
            attachment = MIMEApplication(file.read(), Name=os.path.split(file_path)[1])
            message.attach(attachment)
        
        password = 'uvhr zbmk yeal ujhv'
        s = smtplib.SMTP('smtp.gmail.com', 587)
        s.starttls()
        s.login(sender_email, password)
        s.sendmail(sender_email, receiver_email, message.as_string())
        s.quit()
        return True
    except Exception as e:
        print(f"Email sending failed: {str(e)}")
        return False
    
    
@app.route('/extract', methods=['POST'])
def extract_data():
    data = request.get_json()
    filename = data.get('filename')
    
    if not filename:
        return jsonify({"error": "No filename provided"}), 400
    
    filepath = os.path.join('uploads', filename)
    
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404

    try:
        lst = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        lst.append(row)

        invoice_name = None
        for nest_list in lst:
            for i in nest_list:
                if i:
                    company_lst = i.split('\n')
                    if 'TAX INVOICE' in company_lst:
                        if 'Mogli Labs (India) Pvt Ltd' in company_lst:
                            invoice_name = 'Mogli Labs (India) Pvt Ltd'
                            break
                       
            break
        if not invoice_name:
            print('TAX INVOICE Not Found')
            return jsonify({"error": "TAX INVOICE Not Found"}), 400

        data_dict = {}
     
        for nest_list in lst:
            print(nest_list)
            for i in nest_list:
                if not i is None:
                    data_lst = i.split('\n')
                    if data_lst[0].startswith('Billed From'):
                        for item in data_lst:
                            if item.startswith('Name'):
                                data_dict['Vendor'] = item.split(':', 1)[-1].strip()
                            if item.startswith('GSTIN No'):
                                data_dict['Vendor GSTIN No'] = item.split(':', 1)[-1].strip()
                            if item.startswith('PAN No'):
                                data_dict['Vendor PAN No'] = item.split(':', 1)[-1].strip()
                    if data_lst[0].startswith('Detail of Buyer'):
                        for item in data_lst:
                            if item.startswith('Name'):
                                data_dict['Buyer'] = item.split(':', 1)[-1].strip()
                            if item.startswith('GSTIN No'):
                                data_dict["Buyer's GSTIN No"] = item.split(':', 1)[-1].strip()
                            if item.startswith('PAN No'):
                                data_dict['Buyer PAN No'] = item.split(':', 1)[-1].strip()
                    if data_lst[0].startswith('Invoice No'):
                        for item in data_lst:
                            if item.startswith('Invoice No'):
                                data_dict['Invoice No'] = item.split(':', 1)[-1].strip()
                            if item.startswith('Customer Order No'):
                                customer_order_no = item.split(':', 1)[-1].strip()
                                print('customer_order_no:',customer_order_no)
                                # Validate: must start with '48' and length == 10
                                if not (customer_order_no.startswith('48') and len(customer_order_no) == 10):
                                    print('Customer Order No')
                                    return jsonify({
                                        "error": "Invalid Customer Order No. It must start with '48' and be exactly 10 digits long.",
                                        "extracted_value": customer_order_no
                                    }), 400
                                data_dict['Customer Order No'] = item.split(':', 1)[-1].strip()

                            if item.startswith('Invoice Date'):
                                invoice_date_str = item.split(':', 1)[-1].strip()
                                try:
                                    invoice_date = datetime.strptime(invoice_date_str, '%Y-%m-%d').date()
                                    today = datetime.today().date()
                                    if invoice_date >= today:
                                        print('invoice_date')
                                        return jsonify({
                                            "error": "Invalid Invoice Date. Invoice date cannot be in the future.",
                                            "invoice_date": invoice_date_str
                                        }), 400
                                    data_dict['Invoice Date'] = invoice_date_str
                                except ValueError:
                                    print('in except')
                                    return jsonify({
                                        "error": "Invalid Invoice Date format. Expected format: DD-MM-YYYY.",
                                        "invoice_date": invoice_date_str
                                    }), 400

                    if data_lst[0].startswith('S.No'):
                        break
        print('data_dict::::::::::::::::',data_dict)
        # Extract item table
        req_lst = []
        for j, i in enumerate(lst):
            if i[0] == 'S.No':
                req_lst.append(i)
                for k in range(j+1, len(lst)):
                    if lst[k][0] and lst[k][0].isnumeric():
                        req_lst.append(lst[k])
                break

        final_result = []
        if req_lst:
            header_lst = [str(h) if h is not None else '' for h in req_lst[0]]
            cnt = 0
            for i in range(1, len(req_lst)):
                if req_lst[i][0] and req_lst[i][0].isnumeric():
                    if int(req_lst[i][0]) > cnt:
                        row_data = [str(cell) if cell is not None else '' for cell in req_lst[i]]
                        final_result.append(dict(zip(header_lst, row_data)))
                        cnt += 1

        # Add item numbers
        final_result_with_item = [{"item": idx + 1, **entry} for idx, entry in enumerate(final_result)]
        data_dict['item_lst'] = final_result_with_item

        #         # Save extracted data to templates folder
        # timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        original_filename = data.get('original_filename', 'extracted_data')
        template_filename = f"{original_filename}.json"
        template_path = os.path.join('templates', template_filename)

        with open(template_path, 'w') as f:
            json.dump(data_dict, f, indent=4)

        print('file_nam eejlnekeno:',filename,'data_dict::',data_dict)
        # Send email with extracted data and PDF
        email_sent = send_mail(data_dict, filepath)

        # Clean up temporary file
        if os.path.exists(filepath):
            os.remove(filepath)

        return jsonify({
            "success": True,
            "data": data_dict,
            "saved_file": template_filename,
            "email_sent": email_sent,  # Add this line
            "message": f"Data extracted successfully, saved as {template_filename}" + 
                    (" and emailed successfully!" if email_sent else " but email sending failed.")
        })

    except Exception as e:
        return jsonify({"error": f"Error processing PDF: {str(e)}"}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        return send_file(os.path.join('templates', filename), as_attachment=True)
    except Exception as e:
        return jsonify({"error": "File not found"}), 404

if __name__ == '__main__':
    app.run(debug=True)