from flask import Flask, request, render_template_string, redirect, url_for, send_from_directory, session, make_response
from werkzeug.utils import secure_filename
import PyPDF2
import uuid
import os
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from datetime import datetime
import io

app = Flask(__name__)
app.secret_key = 'your_secret_key'
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def extract_text_from_pdf(path):
    with open(path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        text = ""
        for page in reader.pages:
            content = page.extract_text()
            if content:
                text += content
    return text

def extract_skills(text):
    SKILL_KEYWORDS = {
        'technical': [
            'machine learning', 'ai', 'data analysis', 'python', 'sql', 'java', 'c++',
            'cybersecurity', 'cloud', 'git', 'django', 'javascript', 'tensorflow',
            'pytorch', 'scikit-learn', 'data visualization', 'tableau', 'power bi'
        ],
        'soft': [
            'problem solving', 'communication', 'leadership', 'project management',
            'teamwork', 'creative thinking', 'critical thinking', 'time management'
        ]
    }
    text_lower = text.lower()
    found_skills = {'technical': [], 'soft': []}
    for category, skills in SKILL_KEYWORDS.items():
        for skill in skills:
            if skill in text_lower:
                found_skills[category].append(skill)
    return found_skills

# 2025 Market-Based Skill Importance (customize as needed)
IMPORTANCE_WEIGHTS = {
    'machine learning': 16,
    'ai': 16,
    'data analysis': 12,
    'python': 9,
    'problem solving': 9,
    'communication': 9,
    'leadership': 9,
    'project management': 9,
    'teamwork': 8,
    'cybersecurity': 8,
    'cloud': 8,
    'sql': 7,
    'creative thinking': 6,
    'java': 40,     # Example: for Java developer, Java prioritized
    'c++': 4,
}

def compute_job_weights(required_skills):
    # Only use market importance for skills present in jobdesc, others divide leftover weight
    weights = []
    assigned = []
    for skill in required_skills:
        market_weight = IMPORTANCE_WEIGHTS.get(skill.lower())
        if market_weight is not None:
            weights.append(market_weight)
            assigned.append(True)
        else:
            weights.append(None)
            assigned.append(False)
    total_assigned = sum(w for w in weights if w is not None)
    missing_count = assigned.count(False)
    # Distribute any leftover weight if some skills have no market mapping
    default_weight = ((100 - total_assigned)/missing_count) if missing_count > 0 else 0
    for i in range(len(weights)):
        if weights[i] is None:
            weights[i] = round(default_weight,1)
    # Normalize in case of rounding errors
    total = sum(weights)
    weights = [round(w*100/total,1) for w in weights]
    return dict(zip(required_skills, weights))

def make_pie_chart(skills, weights, statuses):
    # Create pie chart and save to BytesIO buffer
    matched_weights = [weights[s] for s in skills if statuses[s] == 'Matched']
    lacking_weights = [weights[s] for s in skills if statuses[s] == 'Lacking']
    data = []
    labels = []
    colors_pie = []
    for s in skills:
        data.append(weights[s])
        labels.append(f"{s.title()} ({statuses[s]})")
        colors_pie.append("#27ae60" if statuses[s] == 'Matched' else "#c0392b")
    plt.figure(figsize=(5.2,5.2))
    plt.pie(data, labels=labels, colors=colors_pie, startangle=140, autopct='%.1f%%',
            wedgeprops={"edgecolor":"white"}, textprops={'fontsize':10})
    plt.title("Skill Market Weights (% matched/lacking)", fontsize=14, color='#0078D7')
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    plt.close()
    buf.seek(0)
    return buf

HTML_HOME = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <title>Resume Skill Gap Analyzer - Upload</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f4f7f8; color: #333; margin: 0; }
        .container { max-width: 720px; margin: 60px auto; background: white; padding: 40px 35px 32px 35px;
            border-radius: 10px; box-shadow: 0 6px 25px rgba(0,0,0,0.1); text-align: center;}
        h1 { color: #0078D7; margin-bottom: 36px;}
        .upload-box { border: 2px dashed #bbb; border-radius: 12px; padding: 30px 20px 20px 20px; background: #f8f9fa; margin-bottom: 28px;}
        label { font-weight: 600; display: block; margin-bottom: 10px; color: #555; text-align: left;}
        input[type="file"], input[type="text"], input[type="email"] { width: 100%; padding: 10px 12px; border: 1px solid #ccd0d5; border-radius: 7px; margin-bottom: 22px; box-sizing: border-box;}
        .form-btns { display: flex; justify-content: center; gap: 23px; margin-top: 15px; }
        .btn-main, .btn-preview {
            background-color: #0078D7; color: white; font-weight: 600; border: none; padding: 14px 36px; border-radius: 8px; cursor: pointer; font-size: 1.1rem; transition: background-color 0.2s;
        }
        .btn-main:hover, .btn-preview:hover { background-color: #005fa3; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Resume Skill Gap Analyzer</h1>
        <form action="/" method="post" enctype="multipart/form-data" id="upform">
            <div class="upload-box">
                <label for="name">Your Name:</label>
                <input id="name" type="text" name="name" placeholder="Enter your full name" required>
                <label for="email">Your Email:</label>
                <input id="email" type="email" name="email" placeholder="Enter your email" required>
                <label for="resume">Upload Resume (PDF):</label>
                <input id="resume" type="file" name="resume" accept=".pdf" required>
                <label for="jobdesc">Upload Job Description (PDF):</label>
                <input id="jobdesc" type="file" name="jobdesc" accept=".pdf" required>
                <div class="form-btns">
                    <button class="btn-main" name="action" value="analyze" type="submit">Analyze Skills</button>
                    <button class="btn-preview" name="action" value="preview" formnovalidate type="submit">Preview Documents</button>
                </div>
            </div>
        </form>
    </div>
</body>
</html>
"""

HTML_PREVIEW = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <title>Preview Documents - Resume Skill Gap Analyzer</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f4f7f8; margin: 0; }
        .container { max-width: 900px; margin: 45px auto; background: white; padding: 34px 40px; border-radius: 10px; box-shadow: 0 6px 25px rgba(0,0,0,0.11); text-align: center;}
        h1 { color: #0078D7; margin-bottom: 30px;}
        .preview-wrapper { display: flex; justify-content: space-around; gap: 30px; flex-wrap: wrap;}
        .preview-box { flex: 1 1 40%; max-width: 45%;}
        .preview-box h3 { margin-bottom: 10px; color: #0078D7;}
        embed { width: 100%; height: 550px; border: 1px solid #ddd; border-radius: 6px;}
        .btn-analyze { background-color: #0078D7; color: white; font-weight: 600; border: none; padding: 15px 60px; border-radius: 8px; cursor: pointer; font-size: 1.1rem; margin-top: 32px; transition: background 0.2s;}
        .btn-analyze:hover { background-color: #005fa3;}
        .btn-back { margin-top: 22px;display: inline-block; text-decoration: none; color: #0078D7;}
    </style>
</head>
<body>
    <div class="container">
        <h1>Preview Uploaded Documents</h1>
        <div class="preview-wrapper">
            <div class="preview-box">
                <h3>Resume Preview:</h3>
                <embed src="{{ url_for('uploaded_file', filename=resume_filename) }}" type="application/pdf" />
            </div>
            <div class="preview-box">
                <h3>Job Description Preview:</h3>
                <embed src="{{ url_for('uploaded_file', filename=jobdesc_filename) }}" type="application/pdf" />
            </div>
        </div>
        <form action="{{ url_for('analyze') }}" method="post">
            <button class="btn-analyze" type="submit">Analyze Skills</button>
        </form>
        <a class="btn-back" href="{{ url_for('index') }}">&#8592; Back to upload</a>
    </div>
</body>
</html>
"""

HTML_RESULT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <title>Skill Gap Analysis Results</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f4f8; color: #333; padding: 20px;}
        .main-container { max-width: 1020px; margin: 38px auto; background: #fff; border-radius: 10px; box-shadow: 0 4px 24px #dce4ee; padding: 36px 42px;}
        .user-info { text-align: center; margin-bottom: 30px; padding-bottom: 20px; border-bottom: 2px solid #e9ecef;}
        .user-info h2 { color: #0078D7; margin: 0 0 8px 0; font-size: 1.6rem;}
        .user-info p { color: #666; margin: 4px 0; font-size: 1rem;}
        .flex-split { display: flex; gap: 32px; }
        .column { flex: 1; }
        .section-title { font-size: 1.17rem; color: #0078D7; margin-bottom: 18px; font-weight: 600;}
        .skills-container { max-height: 160px; overflow-y: auto; margin-bottom: 16px; padding-right: 8px;}
        .skills-list {margin: 0; padding: 0;}
        .skills-list li {display:inline-block; background:#eef; border-radius:12px; font-size:0.92em; padding:6px 13px; margin:4px 6px 4px 0; white-space: nowrap;}
        .skill-tag { padding: 6px 12px; border-radius: 16px; font-size: 0.92rem; font-weight: 500; margin:4px 6px 4px 0; display: inline-block; white-space: nowrap;}
        .skill-tag.present { background: #d4edda; color: #155724;}
        .skill-tag.tech { background: #cce5ff; color: #004085;}
        .lacking-section { color:#c0392b; margin:18px 0 8px 0; font-size:1.03rem; font-weight:600;}
        .lacking-skill { color:#c0392b; font-weight:600;}
        .all-matched { color:#27ae60; font-weight:600;}
        .chart-container { width:100%; max-width:340px !important; margin:26px auto 36px auto;}
        .stats-grid { display: flex; gap: 14px; justify-content:center; flex-wrap: wrap;}
        .stat-box { flex:1; min-width:85px; text-align: center; padding: 14px 8px; background: #f9fafb; border-radius: 8px;}
        .stat-number { font-size: 1.8rem; font-weight: 700; color: #17a2b8;}
        .stat-label { font-size: 0.76rem; color: #777; text-transform: uppercase; margin-top: 5px;}
        .detailed-skills { margin-top: 12px; max-height: 400px; overflow-y: auto; padding-right: 8px;}
        .detailed-skills h3 { font-size: 1.07rem; color: #0078D7; margin-bottom: 18px;}
        .skill-bar-item { margin-bottom: 14px;}
        .skill-bar-header { display: flex; justify-content: space-between; margin-bottom: 4px;}
        .skill-name { font-size: 0.95rem; font-weight: 600; color: #333;}
        .skill-percent { font-size: 0.92rem; color: #0078D7; font-weight: 600;}
        .skill-bar-bg { height: 11px; background: #e9ecef; border-radius: 10px; overflow: hidden;}
        .skill-bar-fill { height: 100%; border-radius: 10px;}
        .btn-container { display: flex; gap: 16px; justify-content: center; margin-top: 30px;}
        .btn-home, .btn-download { text-decoration: none; background-color: #0078D7; color: white; padding: 13px 32px; border-radius: 6px; font-weight: 600; transition: background-color 0.3s; text-align:center; border: none; cursor: pointer; font-size: 1rem;}
        .btn-home:hover, .btn-download:hover { background-color: #005fa3;}
        .btn-download { background-color: #27ae60;}
        .btn-download:hover { background-color: #1e8449;}
        @media (max-width:870px) {
            .flex-split { flex-direction: column; gap: 18px;}
            .main-container { padding:18px 4vw;}
        }
    </style>
</head>
<body>
    <div class="main-container">
    <div class="user-info">
        <h2>{{ user_name }}</h2>
        <p>{{ user_email }}</p>
        <p style="color:#999; font-size:0.9rem;">Analysis Date: {{ analysis_date }}</p>
    </div>
    <div class="flex-split">
      <div class="column">
        <div class="section-title">Required Skills</div>
        <div class="skills-container">
        <ul class="skills-list">
            {% for skill in required_skills %}
            <li>{{ skill }}</li>
            {% endfor %}
        </ul>
        </div>
        <div class="section-title">Resume Skills</div>
        <div class="skills-container">
            {% for skill in resume_all_skills %}
                {% if skill in matching_skills %}
                    <span class="skill-tag present">{{ skill }}</span>
                {% else %}
                    <span class="skill-tag tech">{{ skill }}</span>
                {% endif %}
            {% endfor %}
        </div>
        <div class="lacking-section">Lacking Skills</div>
        <div class="skills-container">
        {% if missing_skills %}
            <ul>
            {% for skill in missing_skills %}
                <li class="lacking-skill">{{ skill }}</li>
            {% endfor %}
            </ul>
        {% else %}
            <div class="all-matched">All required skills are matched!</div>
        {% endif %}
        </div>
      </div>
      <div class="column">
        <div class="section-title">Skill Distribution</div>
        <div class="chart-container">
            <canvas id="skillChart"></canvas>
        </div>
        <div class="stats-grid">
            <div class="stat-box">
                <div class="stat-number">{{ matched_count }}</div>
                <div class="stat-label">Matched</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">{{ lacking_count }}</div>
                <div class="stat-label">Lacking</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">{{ total_skills }}</div>
                <div class="stat-label">Total</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">{{ pie_data[0] }}%</div>
                <div class="stat-label">Suitability</div>
            </div>
        </div>
        <div class="detailed-skills">
            <h3>Detailed Skills Breakdown</h3>
            {% for skill in detailed_skills %}
            <div class="skill-bar-item">
                <div class="skill-bar-header">
                    <span class="skill-name">{{ skill.name }}</span>
                    <span class="skill-percent">{{ skill.percent }}%</span>
                </div>
                <div class="skill-bar-bg">
                    <div class="skill-bar-fill" style="width: {{ skill.percent }}%; background: {{ 'linear-gradient(90deg, #27ae60, #27ae60)' if skill.name|lower in matching_skills else 'linear-gradient(90deg, #f4d03f, #c0392b)' }};">
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
      </div>
    </div>
        <div class="btn-container">
            <a class="btn-home" href="{{ url_for('index') }}">Upload New Files</a>
            <form action="{{ url_for('download_pdf') }}" method="post" style="display:inline;">
                <button class="btn-download" type="submit">Download PDF Report</button>
            </form>
        </div>
    </div>
    <script>
        const ctx = document.getElementById('skillChart').getContext('2d');
        new Chart(ctx, {
            type: 'pie',
            data: {
                labels: {{ pie_labels|tojson }},
                datasets: [{
                    data: {{ pie_data|tojson }},
                    backgroundColor: {{ pie_colors|tojson }},
                    borderWidth: 2,
                    borderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { font: { size: 13 } }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                let lbl = context.label || '';
                                let val = context.parsed || 0;
                                return lbl + ': ' + val + '%';
                            }
                        }
                    }
                }
            }
        });
    </script>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        action = request.form.get("action")
        name = request.form.get("name", "")
        email = request.form.get("email", "")
        resume_file = request.files.get('resume')
        jobdesc_file = request.files.get('jobdesc')
        if not resume_file or not jobdesc_file:
            return render_template_string(HTML_HOME)
        resume_filename = secure_filename(str(uuid.uuid4()) + '_' + resume_file.filename)
        jobdesc_filename = secure_filename(str(uuid.uuid4()) + '_' + jobdesc_file.filename)
        resume_path = os.path.join(app.config['UPLOAD_FOLDER'], resume_filename)
        jobdesc_path = os.path.join(app.config['UPLOAD_FOLDER'], jobdesc_filename)
        resume_file.save(resume_path)
        jobdesc_file.save(jobdesc_path)
        session['resume'] = resume_filename
        session['jobdesc'] = jobdesc_filename
        session['user_name'] = name
        session['user_email'] = email

        if action == "preview":
            return redirect(url_for('preview'))
        elif action == "analyze":
            return redirect(url_for('analyze'))
    return render_template_string(HTML_HOME)

@app.route("/preview", methods=["GET"])
def preview():
    resume_filename = session.get('resume')
    jobdesc_filename = session.get('jobdesc')
    if not resume_filename or not jobdesc_filename:
        return redirect(url_for('index'))
    return render_template_string(HTML_PREVIEW,
                                 resume_filename=resume_filename,
                                 jobdesc_filename=jobdesc_filename)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route("/analyze", methods=["GET", "POST"])
def analyze():
    resume_filename = session.get('resume')
    jobdesc_filename = session.get('jobdesc')
    user_name = session.get('user_name', 'User')
    user_email = session.get('user_email', '')
    if not resume_filename or not jobdesc_filename:
        return redirect(url_for('index'))
    resume_path = os.path.join(app.config['UPLOAD_FOLDER'], resume_filename)
    jobdesc_path = os.path.join(app.config['UPLOAD_FOLDER'], jobdesc_filename)
    resume_text = extract_text_from_pdf(resume_path)
    jobdesc_text = extract_text_from_pdf(jobdesc_path)
    resume_skills = extract_skills(resume_text)
    jobdesc_skills = extract_skills(jobdesc_text)
    resume_all = set(resume_skills['technical'] + resume_skills['soft'])
    jobdesc_all = set(jobdesc_skills['technical'] + jobdesc_skills['soft'])
    matching_skills = sorted(resume_all & jobdesc_all)
    required_skills = sorted(jobdesc_all)
    lacking_skills = sorted(jobdesc_all - resume_all)
    matched_count = len(matching_skills)
    lacking_count = len(lacking_skills)
    total_skills = len(required_skills)
    weights = compute_job_weights(required_skills)

    status_map = {}
    for skill in required_skills:
        if skill in matching_skills:
            status_map[skill] = 'Matched'
        else:
            status_map[skill] = 'Lacking'

    matched_percent = sum(weights[skill] for skill in matching_skills)
    lacking_percent = sum(weights[skill] for skill in lacking_skills)
    detailed_skills = [{'name': skill.title(), 'percent': round(weights[skill], 1)} for skill in required_skills]
    pie_data = [round(matched_percent, 1), round(lacking_percent, 1)]
    pie_colors = ["#27ae60", "#c0392b"]
    pie_labels = ["Matched %", "Lacking %"]

    # Save analysis data for PDF generation
    session['analysis_data'] = {
        'user_name': user_name,
        'user_email': user_email,
        'resume_all_skills': sorted(resume_all),
        'matching_skills': matching_skills,
        'missing_skills': lacking_skills,
        'required_skills': required_skills,
        'matched_count': matched_count,
        'lacking_count': lacking_count,
        'total_skills': total_skills,
        'pie_data': pie_data,
        'detailed_skills': detailed_skills,
        'weights': weights,
        'status_map': status_map
    }
    return render_template_string(HTML_RESULT,
        user_name=user_name,
        user_email=user_email,
        analysis_date=datetime.now().strftime("%B %d, %Y"),
        resume_all_skills=sorted(resume_all),
        matching_skills=matching_skills,
        missing_skills=lacking_skills,
        required_skills=required_skills,
        matched_count=matched_count,
        lacking_count=lacking_count,
        total_skills=total_skills,
        pie_data=pie_data,
        pie_colors=pie_colors,
        pie_labels=pie_labels,
        detailed_skills=detailed_skills
    )

@app.route("/download_pdf", methods=["POST"])
def download_pdf():
    data = session.get('analysis_data')
    if not data:
        return redirect(url_for('index'))

    buf_img = make_pie_chart(
        data['required_skills'],
        data['weights'],
        data['status_map']
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor('#0078D7'), spaceAfter=12, alignment=1)
    heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#0078D7'), spaceAfter=10)
    normal_style = styles['Normal']
    story = []
    story.append(Paragraph("Skill Gap Analysis Report", title_style))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(f"<b>Candidate:</b> {data['user_name']}", normal_style))
    story.append(Paragraph(f"<b>Email:</b> {data['user_email']}", normal_style))
    story.append(Paragraph(f"<b>Analysis Date:</b> {datetime.now().strftime('%B %d, %Y')}", normal_style))
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph("Summary Statistics", heading_style))
    summary_data = [
        ['Metric', 'Value'],
        ['Total Skills Required', str(data['total_skills'])],
        ['Skills Matched', str(data['matched_count'])],
        ['Skills Lacking', str(data['lacking_count'])],
        ['Suitability (%)', f"{data['pie_data'][0]}%"]
    ]
    summary_table = Table(summary_data, colWidths=[3 * inch, 2 * inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0078D7')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey)
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph("Skill Distribution Pie Chart (Market Weights)", heading_style))
    story.append(Image(buf_img, width=4*inch, height=4*inch))
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph("Required Skills", heading_style))
    story.append(Paragraph(", ".join(data['required_skills']), normal_style))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("Matched Skills", heading_style))
    if data['matching_skills']:
        story.append(Paragraph(", ".join(data['matching_skills']), normal_style))
    else:
        story.append(Paragraph("No skills matched", normal_style))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("Lacking Skills", heading_style))
    if data['missing_skills']:
        story.append(Paragraph(", ".join(data['missing_skills']), normal_style))
    else:
        story.append(Paragraph("All required skills are matched!", normal_style))
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph("Detailed Skills Breakdown (Weights per market)", heading_style))
    skills_data = [['Skill', 'Weight %', 'Status']]
    for skill in data['detailed_skills']:
        status = 'Matched' if skill['name'].lower() in [s.lower() for s in data['matching_skills']] else 'Lacking'
        skills_data.append([skill['name'], f"{skill['percent']}%", status])
    skills_table = Table(skills_data, colWidths=[2.5 * inch, 1.5 * inch, 1.5 * inch])
    skills_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0078D7')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
    ]))
    story.append(skills_table)
    doc.build(story)
    buffer.seek(0)
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=Skill_Gap_Analysis_{data["user_name"].replace(" ", "_")}.pdf'
    return response

if __name__ == "__main__":
    app.run(debug=True)
