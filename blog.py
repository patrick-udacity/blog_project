import os
import re
import random
import hashlib
import hmac
import time

import webapp2
import jinja2

from string import letters

from google.appengine.ext import db

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
    autoescape = True)

secret = "362UaNCxNqj8Qe30fC1BxDdMtVNtFLZgo7Mn7Wgs"

def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)

def make_secure_val(val):
    return '%s|%s' % (val, hmac.new(secret, val).hexdigest())

def check_secure_val(secure_val):
    val = secure_val.split('|')[0]
    if secure_val == make_secure_val(val):
        return val

class BlogHandler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        params['user'] = self.user
        return render_str(template, **params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def set_secure_cookie(self, name, val):
        cookie_val = make_secure_val(val)
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    def read_userid_cookie(self):
        return self.request.cookies.get('user_id')    

    def login(self, user):
        self.set_secure_cookie('user_id', str(user.key().id()))
        activeUser = str(user.key().name)
        self.response.headers.add_header('Set-Cookie', 'activeUser='
            + activeUser + '; Path=/')
    def logout(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        uid = self.read_secure_cookie('user_id')
        self.user = uid and User.by_id(int(uid))

def render_post(response, post):
    response.out.write('<b>' + post.subject + '</b><br>')
    response.out.write(post.content)


class MainPage(BlogHandler):
  def get(self):
      self.write('Hello, Udacity!')


##### User account creation functions.
def make_salt(length = 5):
    return ''.join(random.choice(letters) for x in xrange(length))

def make_pw_hash(name, pw, salt = None):
    if not salt:
        salt = make_salt()
    h = hashlib.sha256(name + pw + salt).hexdigest()
    return '%s,%s' % (salt, h)

def valid_pw(name, password, h):
    salt = h.split(',')[0]
    return h == make_pw_hash(name, password, salt)

def users_key(group = 'default'):
    return db.Key.from_path('users', group)


#Create the user object for logins.
class User(db.Model):
    name = db.StringProperty(required = True)
    pw_hash = db.StringProperty(required = True)
    email = db.StringProperty()

    @classmethod
    def by_id(cls, uid):
        return cls.get_by_id(uid, parent = users_key())

    @classmethod
    def by_name(cls, name):
        u = cls.all().filter('name =', name).get()
        return u

    @classmethod
    def register(cls, name, pw, email = None):
        pw_hash = make_pw_hash(name, pw)
        return cls(parent = users_key(),
                    name = name,
                    pw_hash = pw_hash,
                    email = email)

    @classmethod
    def login(cls, name, pw):
        u = cls.by_name(name)
        if u and valid_pw(name, pw, u.pw_hash):
            return u

##### Functions for blog post creations.
def blog_key(name = 'default'):
    return db.Key.from_path('blogs', name)

    
#Single blog post object.
class Post(db.Model):
    subject = db.StringProperty(required = True)
    content = db.TextProperty(required = True)
    comment_list = db.StringListProperty(required = True)
    author = db.StringProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now = True)
    likes = db.IntegerProperty(required = False)
    liked_by = db.StringProperty(required = False)
    

    def render(self):
        self._render_text = self.content.replace('\n', '<br>')
        return render_str("post.html", p = self)


#Front end handler
class BlogFront(BlogHandler):
    def get(self):
        posts = Post.all().order('-created')
        self.render('front.html', posts = posts)


#Post page handler
class PostPage(BlogHandler):
    
    def get(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        if not post:
            
            #self.error(404)
            self.redirect('/blog')
            return

        self.render("permalink.html", post = post)

    def post(self, post_id):
        error = ""
        confirmation = ""
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        #This list will be used to extract an entity's comments.
        comment_list = []

        if not post:
            self.error(404)
            self.redirect('/blog')
            
            return

        #Check to see if a user is logged in.
        if not self.user:
            userunknown_error = "You must login to 'Like/Unlike/Edit' a post."
            self.render("login-form.html", post = post,
                userunknown_error = userunknown_error)
            return

        #Prohibit authors from liking their own posts.
        if ((self.user.name == post.author) and ((self.request.get('form_name')
            == 'like' or self.request.get('form_name') == 'unlike'))):
            error = "You can't 'Like/Unlike' your own post. No changes made."
            self.render("permalink.html", post = post, error = error)
            return

        #Process a request to like a blog entry.     
        if self.request.get('form_name') == 'like':
                #Make sure the user does not already like the post.
                #Like allowed
                if (post.liked_by.find(self.user.name) == -1):
                    post.likes = post.likes + 1
                    post.liked_by = ','.join((post.liked_by,self.user.name))
                    post.put()
                    message = " (Liked by you.)"
                    confirmation = "You have now 'Liked' this blog entry."
                    self.render("permalink.html", post = post,
                        confirmation = confirmation, message = message)
                    return
                #Like blocked
                else:
                    error = ("You have already 'Liked' this blog entry. "
                        + "No changes made.")
                    message = " (Liked by you.)"
                    self.render("permalink.html", post = post,
                        error = error, message = message)
                    return
        
        #Process a request to unlike a blog entry.
        elif self.request.get('form_name') == 'unlike':
            #Make sure that the user currenty likes the post.
            #Unlike blocked
            if (post.liked_by.find(self.user.name) == -1):
                    error = ("You have not 'liked' this entry yet - no "
                        + "'unlike' can be done. No changes made.")
                    self.render("permalink.html", post = post, error = error)
                    return
                
            #Unlike allowed
            else:
                post.likes = post.likes - 1
                post.liked_by = (post.liked_by.replace(","
                    + self.user.name , ""))
                post.put()
                confirmation = "You have now 'Unliked' this blog entry."
                self.render("permalink.html", post = post,
                    confirmation = confirmation)
                return

        #Process a request to update a blog entry.
        elif self.request.get('form_name') == 'update_post':

            #Make sure updater is the author of the blog entry.
            #Update blocked
            if not self.user.name == post.author:
                error = "You are not authorized to update this post."
                self.render("permalink.html", post = post, error = error)
                return
            #Update allowed
            elif self.user.name == post.author:
                self.render("updatepost.html", post = post)

        #Add the updates to the Post entity.
        elif self.request.get('form_name') == 'update_complete':
            
            post.subject = self.request.get('subject')
            post.content = self.request.get('content')
            post.put()
        
            confirmation = "Post has been updated."
            self.render("permalink.html", post = post,
                confirmation = confirmation)
            return

        #Cancel post update submission.
        elif self.request.get('form_name') == 'update_cancelled':
            self.render("permalink.html", post = post)
            return

        #Initiate the add a comment page.
        elif self.request.get('form_name') == 'comment':
            self.render("comment.html", post = post)
            return
        
        #Submit a comment for addition to an entity.
        elif self.request.get('form_name') == 'submit_comment':
            # The ^ character will be used as a delimiter
            # in the stored comment list members.
            signature = (str(self.user.name).upper()
                + str(time.strftime(" on %m/%d/%Y at %I:%M %p(GMT):" + "^")))
            content = (signature +
                str(self.request.get('comment_content')))
            post.comment_list.append(content)
            post.put()
            self.render("permalink.html", post = post)
            return

        #Initiate the update of a comment page.
        #Make sure updater is the author of the comment.
        #Confirm author 
        elif self.request.get('form_name') == 'edit_comment':
            active_content  = self.request.get('active_comment')
            if self.user.name.upper() in active_content:      
                self.render("edit_comment.html", post = post,
                    active_content = active_content.split('^',1)[1],
                    comment_object = active_content.split('^',1)[0])
                return
            else:
                error = self.user.name.upper() + (
                    ", you are not authorized to edit this comment.")
                self.render("permalink.html", post = post, error = error)
                return
        
        #Update an existing comment.
        elif self.request.get('form_name') == 'update_comment':
            # The ^ character will be used as a
            #delimiter in the stored comment list members.
            comment_object  = self.request.get('comment_object')

            #Select the comment from list of comments
            #by matching the comment text.
            comment_index = ([i for i, s in
                enumerate(post.comment_list) if comment_object in s])
            
            comment_text = self.request.get('comment_content')
            signature = (str(self.user.name).upper()
                + str(time.strftime(" on %m/%d/%Y at %I:%M %p(GMT):" + "^")))
            content = (signature + comment_text)
            
            post.comment_list[comment_index[0]] = content
            post.put()
            self.render("permalink.html", post = post)
            return        

        #Delete a comment.
        #Make sure updater is the author of the comment.
        #Confirm author 
        elif self.request.get('form_name') == 'delete_comment':
            comment_object  = self.request.get('comment_object')
            if self.user.name.upper() in comment_object:
                
                #Select the comment from list of
                #comments by matching the comment text.
                comment_index = ([i for i, s in
                    enumerate(post.comment_list) if comment_object in s])
                     
                #Delete the comment.
                del post.comment_list[comment_index[0]]
                post.put()
                posts = Post.all().order('-created')
                self.render('front.html', posts = posts)
                return  
            else:
                error = self.user.name.upper() + (
                    ", you are not authorized to edit this comment.")
                self.render("permalink.html", post = post, error = error)
                return        

        #Cancel comment submission.
        elif self.request.get('form_name') == 'cancel_comment':
            self.render("permalink.html", post = post)
            return
    
        #Initiate the deletion of a post.
        elif self.request.get('form_name') == 'delete_post':
            #Make sure updater is the author of the blog entry.
            #Confirm author
            if self.user.name == post.author:
                self.render("confirmdelete.html")
                return
            #Post deletion blocked for non author
            else:
                if not self.user.name == post.author:
                    error = "You are not authorized to delete this post."
                    self.render("permalink.html", post = post, error = error)
                    return

        #Delete a post.
        elif self.request.get('form_name') == 'delete_yes':
            #Make sure updater is the author of the blog entry.
            #Confirm author
            if self.user.name == post.author:
                db.delete(key)
                posts = Post.all().order('-created')
                self.redirect('/blog')
                return

        #Deletion Cancelled.
        elif self.request.get('form_name') == 'delete_cancel':
            self.render("permalink.html", post = post)
            return 
                           

#Handler for a new post
class NewPost(BlogHandler):
    def get(self):
        if self.user:
            self.render("newpost.html")
        else:
            self.redirect("/login")

    def post(self):
        if not self.user:
            self.redirect('/blog')

        subject = self.request.get('subject')
        content = self.request.get('content')
        author  = self.user.name
        likes = 0
        liked_by = ""
        comments = ""
        
        if subject and content:
            p = (Post(parent = blog_key(), subject = subject,
                content = content, author = author, likes = likes,
                liked_by = liked_by))
            p.put()
            self.redirect('/blog/%s' % str(p.key().id()))
        else:
            error = "subject and content, please!"
            self.render("newpost.html", subject=subject,
                content=content, error=error)


#User account name validation.
USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
def valid_username(username):
    return username and USER_RE.match(username)

#Password validation
PASS_RE = re.compile(r"^.{3,20}$")
def valid_password(password):
    return password and PASS_RE.match(password)

#Email validation
EMAIL_RE  = re.compile(r'^[\S]+@[\S]+\.[\S]+$')
def valid_email(email):
    return not email or EMAIL_RE.match(email)


#Signup for new account handler.
#This helps structure the account properties.
class Signup(BlogHandler):
    def get(self):
        self.render("signup-form.html")

    def post(self):
        have_error = False
        self.username = self.request.get('username')
        self.password = self.request.get('password')
        self.verify = self.request.get('verify')
        self.email = self.request.get('email')

        params = dict(username = self.username,
                      email = self.email)

        if not valid_username(self.username):
            params['error_username'] = "That's not a valid username."
            have_error = True

        if not valid_password(self.password):
            params['error_password'] = "That wasn't a valid password."
            have_error = True
        elif self.password != self.verify:
            params['error_verify'] = "Your passwords didn't match."
            have_error = True

        if not valid_email(self.email):
            params['error_email'] = "That's not a valid email."
            have_error = True

        if have_error:
            self.render('signup-form.html', **params)
        else:
            self.done()

    def done(self, *a, **kw):
        raise NotImplementedError



#Register a new account handler.
class Register(Signup):
    def done(self):
        #make sure the user doesn't already exist
        u = User.by_name(self.username)
        if u:
            msg = 'That user already exists.'
            self.render('signup-form.html', error_username = msg)
        else:
            u = User.register(self.username, self.password, self.email)
            u.put()

            self.login(u)
            self.redirect('/blog')

#Login handler.
class Login(BlogHandler):
    def get(self):
        self.render('login-form.html')

    def post(self):
        username = self.request.get('username')
        password = self.request.get('password')

        u = User.login(username, password)
        if u:
            self.login(u)
            self.redirect('/blog')
        else:
            msg = 'Invalid login'
            self.render('login-form.html', error = msg)


#Logout handler
class Logout(BlogHandler):
    def get(self):
        self.logout()
        self.redirect('/blog')



#Url handlers.
app = webapp2.WSGIApplication([('/', BlogFront),
                               ('/blog/?', BlogFront),
                               ('/blog/([0-9]+)', PostPage),
                               ('/blog/newpost', NewPost),
                               ('/signup', Register),
                               ('/login', Login),
                               ('/logout', Logout),
                               ],
                              debug=True)
