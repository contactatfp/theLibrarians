import os, openai, datetime, requests, io
from PIL import Image
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from fpdf import FPDF
from werkzeug.utils import send_file
import json

from forms import RegistrationForm, LoginForm, PostForm

app = Flask(__name__)
app.config['SECRET_KEY'] = '579162jfkdlsasnfnjs2el42dkjd'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager(app)
app.app_context().push()
# openai.api_key = os.getenv("OPENAI_API_KEY")

with open('config.json') as f:
    config = json.load(f)

openai.api_key = config['api_secret']


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    image_file = db.Column(db.String(20), nullable=False, default='default.jpg')
    password = db.Column(db.String(60), nullable=False)
    posts = db.relationship('Post', backref='author', lazy=True)
    books = db.relationship('Book', backref='author', lazy=True)

    def __repr__(self):
        return f"User('{self.username}', '{self.email}', '{self.image_file}')"


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    child_name = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f"Post('{self.title}', '{self.date_posted}')"


class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f"Book('{self.content}')"


@app.route('/')
def home():  # put application's code here
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash(f'Account created for {form.username.data}!', 'success')
        return redirect(url_for('home'))
    return render_template('register.html', title='Register', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            flash('You have been logged in!', 'success')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')
    return render_template('login.html', title='Login', form=form)


@app.route('/about')
def about():  # put application's code here
    return render_template('about.html')


@app.route('/book')
def book():  # put application's code here
    return render_template('book.html')


def get_image(prompt):
    response = openai.Image.create(
        prompt=prompt,
        n=1,
        size="512x512",
    )
    image_url = response['data'][0]['url']
    return image_url


@app.route('/form', methods=['GET', 'POST'])
def form():
    login_required(current_user)
    if not current_user.is_authenticated:
        return redirect(url_for('home'))
    form = PostForm()
    user = current_user
    if form.validate_on_submit():
        post = Post(title=form.title.data, content=form.content.data, age=form.age.data, author=user,
                    child_name=form.child_name.data)

        # openai.api_key = os.getenv("OPEN_API_KEY")
        book = form.content.data
        response = openai.Completion.create(
            model="text-davinci-003",
            prompt=book,
            temperature=0.6,
            max_tokens=300,
        )
        image_url = get_image(book)
        userBook = Book(content=response.choices[0].text, author=user)
        db.session.add(post)
        db.session.add(userBook)
        db.session.commit()
        flash('Your book is being created!', 'success')
        # return redirect(url_for('book', book=userBook.content))
        return render_template('book.html', book=userBook, image_url=image_url, post=post)
    return render_template('form.html', title='New Post', form=form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/initdb')
def initdb():
    db.create_all()
    return 'Initialized the database'

@app.route('/all')
def all():
    return render_template('all.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=True)

