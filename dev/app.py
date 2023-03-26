import os, openai, datetime, requests, io
from PIL import Image
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from fpdf import FPDF
from werkzeug.utils import send_file
import json
from io import BytesIO
from flask_caching import Cache

from forms import RegistrationForm, LoginForm, PostForm

cache = Cache()


app = Flask(__name__)
app.config['SECRET_KEY'] = '579162jfkdlsasnfnjs2el42dkjd'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://librarians:Postgres1@librarians.postgres.database.azure.com/postgres?sslmode=require'
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
app.config['CACHE_TYPE'] = 'SimpleCache'
cache.init_app(app)

app.config['SQLALCHEMY_POOL_SIZE'] = 15
app.config['SQLALCHEMY_MAX_OVERFLOW'] = 5
app.config['SQLALCHEMY_POOL_RECYCLE'] = 360

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


db.create_all()


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
        login_user(user)
        return redirect(url_for('form'))
    return render_template('register.html', title='Register', form=form)


def generate_pdf(post, book, image_url):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=24)

    # Save image to a buffer
    response = requests.get(image_url)
    image_data = io.BytesIO(response.content)

    # Open the image with PIL, convert to JPEG, and save to a new buffer
    image = Image.open(image_data)
    image_rgb = image.convert("RGB")
    image_buffer = io.BytesIO()
    image_rgb.save(image_buffer, format="JPEG")
    image_buffer.seek(0)

    # Save the converted image to a temporary file
    temp_image_name = "temp_image_{}.jpg".format(current_user.id)
    with open(temp_image_name, "wb") as temp_image_file:
        temp_image_file.write(image_buffer.read())

    # Add the image to the PDF
    pdf.image(temp_image_name, x=20, y=30, w=170, h=170)
    pdf.set_font("Arial", size=12)
    pdf.set_xy(10, 210)
    pdf.multi_cell(0, 10, book.content)

    # Remove the temporary image file
    os.remove(temp_image_name)

    # Add text and format the PDF
    # (The rest of your original generate_pdf function)

    return pdf.output(dest="S").encode("latin1")



@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            flash('You have been logged in!', 'success')
            return redirect(next_page) if next_page else redirect(url_for('form'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')
    return render_template('login.html', title='Login', form=form)


@app.route('/about')
def about():  # put application's code here
    return render_template('about.html')


@app.route('/book')
def book():  # put application's code here
    userBook_content = request.args.get('book_content')
    image_url = request.args.get('image_url')
    post_title = request.args.get('post_title')
    pdf_key = request.args.get('pdf_key')
    return render_template('book.html', book_content=userBook_content, image_url=image_url, post_title=post_title, pdf_key=pdf_key)


def get_image(prompt):
    response = openai.Image.create(
        prompt=prompt,
        n=1,
        size="512x512",
    )
    image_url = response['data'][0]['url']
    return image_url


@app.route('/form', methods=['GET', 'POST'])
@login_required
def form():
    if not current_user.is_authenticated:
        return redirect(url_for('home'))
    form = PostForm()
    user = current_user
    if form.validate_on_submit():
        post = Post(title=form.title.data, content=form.content.data, age=form.age.data, author=user,
                    child_name=form.child_name.data)
        # book = form.content.data
        book = 'Create a childrens story about ' + form.child_name.data + ' who is ' + str(
            form.age.data) + ' years old. The story should be about ' + form.title.data + '. ' + form.content.data

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
        pdf_buffer = generate_pdf(post, userBook, image_url)
        pdf_key = f'pdf_buffer_{current_user.id}'  # Create a unique key for the user
        cache.set(pdf_key, pdf_buffer, timeout=300)  # Store the PDF buffer in the cache for 5 minutes

        return redirect(url_for('book', book_content=userBook.content, image_url=image_url, post_title=post.title, pdf_key=pdf_key))

    return render_template('form.html', title='New Post', form=form)


@app.route('/download_pdf/<pdf_key>')
@login_required
def download_pdf(pdf_key):
    # pdf_buffer = session.get('pdf_buffer')
    pdf_buffer = cache.get(pdf_key)
    if pdf_buffer:
        return send_file(BytesIO(pdf_buffer), request.environ, mimetype='application/pdf', as_attachment=True, download_name='book.pdf')
    else:
        flash('There was an error generating the PDF. Please try again.', 'danger')
        return redirect(url_for('form'))



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
    now = datetime.datetime.utcnow()
    latest = Post.query.filter(Post.date_posted <= now).limit(10).all()
    return render_template('all.html', title="Browse All", posts=latest)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=True)
