from flask import Flask
import app

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer(), primary_key=True)
    username = db.Column(db.VARCHAR(20))
    email = db.Column(db.VARCHAR(120), unique=true)
    image_file = db.Column(db.VARCHAR(20))
    password = db.Column(db.VARCHAR(60))

class Book(db.Model):
    __tablename__ = "books"
    id = db.Column(db.Integer(), primary_key=True)
    content = db.Column(db.Text())
    user_id = db.Column(db.Integer())

class Post(db.Model):
    __tablename__ = "posts"
    id = db.Column(db.Integer(), primary_key=True)
    child_name = db.Column(db.VARCHAR(100))
    title = db.Column(db.VARCHAR(100))
    age = db.Column(db.Integer())
    date_posted = db.Column(db.DATETIME())
    content = db.Column(db.Text())
    user_id = db.Column(db.Integer())