import os, openai, datetime, requests, io, sys
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
from flask import jsonify
from urllib.parse import quote
from azure.storage.blob import BlobServiceClient
from forms import RegistrationForm, LoginForm, PostForm

cache = Cache()

app = Flask(__name__)
app.config['SECRET_KEY'] = '579162jfkdlsasnfnjs2el42dkjd'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
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

# storage_str = os.getenv('AZURE_STORAGE_CONNECTION_STRING')   
storage_str = config['image_connection_string']    # Key for the storage resource
container_name = "quickstoryphotostorage" # Name of the container in Azure
blob_service_client = BlobServiceClient.from_connection_string(conn_str=storage_str) # create a blob service client to interact with the storage account
try:
    container_client = blob_service_client.get_container_client(container=container_name) # get container client to interact with the container in which images will be stored
    container_client.get_container_properties() # get properties of the container to force exception to be thrown if container does not exist
except Exception as e:
    container_client = blob_service_client.create_container(container_name) # create a container in the storage account if it does not exist


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
    image = db.Column(db.Text, nullable=False)  # The url to the image
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f"Post('{self.title}', '{self.date_posted}')"


class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.Text, nullable=False)  # The url to the image
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

@app.route('/share', methods=['POST'])
@login_required
def share():
    data = request.get_json()
    post_title = data.get('post_title')
    post_id = data.get('post_id')

    url = quote(request.url_root + 'book?read=' + str(post_id), safe='')

    share_data = {
        'facebook': f'https://www.facebook.com/sharer/sharer.php?u={url}',
        'twitter': f'https://twitter.com/intent/tweet?url={url}&text={quote(post_title)}',
        'linkedin': f'https://www.linkedin.com/shareArticle?mini=true&url={url}&title={quote(post_title)}',
    }
    return jsonify(share_data)

@app.route('/generate_pdf_download_link', methods=['POST'])
@login_required
def generate_pdf_download_link():
    data = request.get_json()
    post_id = data.get('post_id')
    post = Post.query.filter(Post.id == post_id).first()
    userBook = Book.query.filter(Book.id == post_id).first()
    image_url = None

    pdf_buffer = generate_pdf(post, userBook, image_url)
    pdf_key = f'pdf_buffer_{current_user.id}'  # Create a unique key for the user
    cache.set(pdf_key, pdf_buffer, timeout=300)  # Store the PDF buffer in the cache for 5 minutes

    return jsonify({'pdf_key': pdf_key})



def generate_pdf(post, book, image_url):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=24)

    if image_url:
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

        # Remove the temporary image file
        os.remove(temp_image_name)

    # Add text and format the PDF
    pdf.set_font("Arial", size=12)
    pdf.set_xy(10, 210)
    pdf.multi_cell(0, 10, book.content)
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
    #    print(request.args['read'], file=sys.stderr)
    if 'read' in request.args:
        id = request.args['read']
        post = Post.query.filter(Post.id == id).first()
        userBook = Book.query.filter(Book.id == id).first()
        image_url = None
        post_title = post.title
        userBook_content = userBook.content

        if current_user.is_authenticated:
            pdf_buffer = generate_pdf(post, userBook, image_url)
            pdf_key = f'pdf_buffer_{current_user.id}'  # Create a unique key for the user
            cache.set(pdf_key, pdf_buffer, timeout=300)  # Store the PDF buffer in the cache for 5 minutes
        else:
            pdf_key = None;
    #        return render_template('book.html', book_content=book.content, post_title=post.title)
    else:
        userBook_content = request.args.get('book_content')
        image_url = request.args.get('image_url')
        post_title = request.args.get('post_title')
        pdf_key = request.args.get('pdf_key')

    return render_template('book.html', book_content=userBook_content, image_url=image_url, post_title=post_title,
                           pdf_key=pdf_key)


def get_image(prompt):
    response = openai.Image.create(
        prompt=prompt,
        n=1,
        size="512x512",
    )
    image_url = response['data'][0]['url']
    return image_url


def remove_non_latin1_characters(text):
    return text.encode('latin1', errors='ignore').decode('latin1')


@app.route('/form', methods=['GET', 'POST'])
def form():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    form = PostForm()
    user = current_user
    if form.validate_on_submit():
        sanitized_title = remove_non_latin1_characters(form.title.data)
        sanitized_content = remove_non_latin1_characters(form.content.data)
        sanitized_child_name = remove_non_latin1_characters(form.child_name.data)

        post = Post(title=sanitized_title, content=sanitized_content, age=form.age.data, author=user,
                    child_name=sanitized_child_name)
        # book = form.content.data
        book = 'Create a childrens story about ' + form.child_name.data + ' who is ' + str(
            form.age.data) + ' years old. The story should be about ' + form.title.data + '. ' + form.content.data + 'Limit response to 200 words max.'
        bookForImage = "Create a cartoonish image for a children's storybook cover that conveys a light and happy tone, and is suitable for children ages 1-7. The image should not contain any words. The storybook may contain different characters and settings, so the image should be general and not specific to any particular story. Please use your creativity to come up with a fun and engaging image that will appeal to young children centered around" + form.content.data
        response = openai.Completion.create(
            model="text-davinci-003",
            prompt=book,
            temperature=0.6,
            max_tokens=470,
        )
        image_url = get_image('Art Style: In the style of Raymond Briggs: ' + bookForImage)

        # Save image to a buffer
        image_response = requests.get(image_url)
        image_data = io.BytesIO(image_response.content)
        
        # Open the image with PIL, convert to JPEG, and save to a new buffer
        image = Image.open(image_data)
        image_rgb = image.convert("RGB")
        image_buffer = io.BytesIO()
        image_rgb.save(image_buffer, format="JPEG")
        image_buffer.seek(0)

        # Save the converted image to a temporary file
        temp_image_name = "{}.jpg".format(hash(image_url + book + bookForImage))
        with open(temp_image_name, "wb") as temp_image_file:
            temp_image_file.write(image_buffer.read())

        # Uploading image to storage and getting new url
        with open(temp_image_name, "rb") as data:
            container_client.upload_blob(data.name, data)
        #container_client.upload_blob(temp_image_name, temp_image_name)
        #blob_client = container_client.get_blob_client(temp_image_name)
        new_url = "https://quickstoryphotostorage.blob.core.windows.net/quickstoryphotostorage/" + temp_image_name

        # Remove the temporary image file
        os.remove(temp_image_name)

        userBook = Book(content=response.choices[0].text, author=user, image=new_url)
        post.image = new_url
        db.session.add(post)
        db.session.add(userBook)
        db.session.commit()
        flash('Your book is being created!', 'success')
        # return redirect(url_for('book', book=userBook.content))
        pdf_buffer = generate_pdf(post, userBook, image_url)
        pdf_key = f'pdf_buffer_{current_user.id}'  # Create a unique key for the user
        cache.set(pdf_key, pdf_buffer, timeout=300)  # Store the PDF buffer in the cache for 5 minutes

        return redirect(
            url_for('book', book_content=userBook.content, image_url=image_url, post_title=post.title, pdf_key=pdf_key))

    return render_template('form.html', title='New Post', form=form)


@app.route('/download_pdf/<pdf_key>')
@login_required
def download_pdf(pdf_key):
    # pdf_buffer = session.get('pdf_buffer')
    pdf_buffer = cache.get(pdf_key)
    if pdf_buffer:
        return send_file(BytesIO(pdf_buffer), request.environ, mimetype='application/pdf', as_attachment=True,
                         download_name='book.pdf')
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


@app.route('/browse', methods=['GET'])
def browse():
   # now = datetime.datetime.utcnow()
   # latest = Post.query.filter(Post.date_posted <= now).order_by(Post.date_posted.desc()).limit(10).all()
    page = db.paginate( db.select(Post).order_by(Post.date_posted.desc()), per_page=12 )

    # if "read" in request.form:
        # print("READ", file=sys.stderr)
        # print(request.form.get('read'), file=sys.stderr)
        # # book = Book.query.filter(Book.id == request.form['read']).first()
        # # post = Post.query.filter(Post.id == request.form['read'])
        # # pass
        # # return render_template('book.html', book=book, post=post)
    # elif "page" in request.form:
        # print("PAGE", file=sys.stderr)
    # print("NO READ", file=sys.stderr)
    # print(request.form.get('read'), file=sys.stderr)
    # for field in request.form:
        # print(field, file=sys.stderr)
    iter = page.iter_pages(left_edge=1, right_edge=1, left_current=2, right_current=2)
    return render_template('browse.html', title="Browse Books", posts=page, iter=iter)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=True)
