import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
from dotenv import load_dotenv
from bson import ObjectId
from datetime import datetime

# Load environment variables from .env
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mysecretkey123456!'

# Initialize Bcrypt
bcrypt = Bcrypt(app)

# Initialize MongoDB client
mongo_client = MongoClient(os.getenv('MONGO_URI'))
db = mongo_client['peer_review_portal']

# Collections
users_collection = db['users']
reviews_collection = db['reviews']

# ... routes and logic will go here ...

@app.route('/')
def index():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        
        if users_collection.find_one({'email': email}):
            flash('Email already registered.', 'error')
            return redirect(url_for('register'))
        
        password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        user = {
            'username': username,
            'email': email,
            'password_hash': password_hash,
            'role': role
        }
        users_collection.insert_one(user)
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('registration.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        user = users_collection.find_one({'email': email, 'role': role})
        if user and bcrypt.check_password_hash(user['password_hash'], password):
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Login successful!', 'success')
            if user['role'] == 'student':
                return redirect(url_for('student_dashboard'))
            elif user['role'] == 'guide':
                return redirect(url_for('guide_dashboard'))
            else:
                return redirect(url_for('dashboard'))
        else:
            flash('Invalid email, password, or role.', 'error')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please log in to access the dashboard.', 'error')
        return redirect(url_for('login'))
    current_role = session['role']
    # Show users of the opposite role
    opposite_role = 'guide' if current_role == 'student' else 'student'
    users = list(users_collection.find({'role': opposite_role}))
    return render_template('dashboard.html', users=users, current_role=current_role)

@app.route('/review/<to_user_id>', methods=['GET', 'POST'])
def review(to_user_id):
    if 'user_id' not in session:
        flash('Please log in to submit a review.', 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        score = int(request.form['score'])
        comments = request.form['comments']
        review_doc = {
            'from_user_id': ObjectId(session['user_id']),
            'to_user_id': ObjectId(to_user_id),
            'score': score,
            'comments': comments,
            'created_at': datetime.utcnow()
        }
        reviews_collection.insert_one(review_doc)
        flash('Review submitted successfully!', 'success')
        # Redirect to student dashboard after review
        return redirect(url_for('student_dashboard'))
    # GET: show form
    to_user = users_collection.find_one({'_id': ObjectId(to_user_id)})
    return render_template('review.html', to_user=to_user)

@app.route('/student_dashboard', methods=['GET', 'POST'])
def student_dashboard():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Access denied. Students only.', 'error')
        return redirect(url_for('login'))
    guides = list(users_collection.find({'role': 'guide'}))
    if request.method == 'POST':
        project_title = request.form['project_title']
        github_link = request.form['github_link']
        video_link = request.form['video_link']
        ppt_link = request.form['ppt_link']
        documentation_link = request.form['documentation_link']
        description = request.form['description']
        guide_id = request.form['guide_id']
        review_score = int(request.form['review_score']) if 'review_score' in request.form else None
        project = {
            'student_id': session['user_id'],
            'student_name': session['username'],
            'guide_id': guide_id,
            'project_title': project_title,
            'github_link': github_link,
            'video_link': video_link,
            'ppt_link': ppt_link,
            'documentation_link': documentation_link,
            'description': description,
            'review_score': review_score,
            'created_at': datetime.utcnow()
        }
        db['projects'].insert_one(project)
        flash('Project submitted successfully!', 'success')
        return redirect(url_for('student_dashboard'))
    projects = list(db['projects'].find({'student_id': session['user_id']}))
    # Fetch reviews received for this student, and attach reviewer info
    reviews = list(reviews_collection.find({'to_user_id': ObjectId(session['user_id'])}))
    for review in reviews:
        reviewer = users_collection.find_one({'_id': review['from_user_id']})
        review['reviewer_name'] = reviewer['username'] if reviewer else 'Unknown'
        review['reviewer_email'] = reviewer['email'] if reviewer else ''
    return render_template('student_dashboard.html', guides=guides, projects=projects, reviews=reviews)

@app.route('/guide_dashboard')
def guide_dashboard():
    if 'user_id' not in session or session.get('role') != 'guide':
        flash('Access denied. Guides only.', 'error')
        return redirect(url_for('login'))
    # Fetch projects assigned to this guide
    projects = list(db['projects'].find({'guide_id': session['user_id']}))
    return render_template('guide_dashboard.html', projects=projects)

@app.route('/guide_review/<project_id>', methods=['GET', 'POST'])
def guide_review(project_id):
    if 'user_id' not in session or session.get('role') != 'guide':
        flash('Access denied. Guides only.', 'error')
        return redirect(url_for('login'))
    project = db['projects'].find_one({'_id': ObjectId(project_id)})
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('guide_dashboard'))
    student_id = project['student_id']
    if request.method == 'POST':
        score = int(request.form['score'])
        comments = request.form['comments']
        review_doc = {
            'from_user_id': ObjectId(session['user_id']),
            'to_user_id': ObjectId(student_id),
            'project_id': ObjectId(project_id),
            'score': score,
            'comments': comments,
            'created_at': datetime.utcnow()
        }
        reviews_collection.insert_one(review_doc)
        flash('Review submitted successfully!', 'success')
        return redirect(url_for('guide_dashboard'))
    student = users_collection.find_one({'_id': ObjectId(student_id)})
    return render_template('review.html', to_user=student, project=project)

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

@app.route('/student_reviews')
def student_reviews():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Access denied. Students only.', 'error')
        return redirect(url_for('login'))
    reviews = list(reviews_collection.find({'to_user_id': ObjectId(session['user_id'])}))
    for review in reviews:
        reviewer = users_collection.find_one({'_id': review['from_user_id']})
        review['reviewer_name'] = reviewer['username'] if reviewer else 'Unknown'
        review['reviewer_email'] = reviewer['email'] if reviewer else ''
    return render_template('student_reviews.html', reviews=reviews)

@app.route('/student_projects')
def student_projects():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('Access denied. Students only.', 'error')
        return redirect(url_for('login'))
    projects = list(db['projects'].find({'student_id': session['user_id']}))
    guides = list(users_collection.find({'role': 'guide'}))
    return render_template('student_projects.html', projects=projects, guides=guides)

if __name__ == '__main__':
    app.run(debug=True) 