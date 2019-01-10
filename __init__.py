from flask import Flask, render_template, redirect, url_for
from flask_bootstrap import Bootstrap
from flask_wtf import FlaskForm
from flask import request
from wtforms import StringField, SelectField, FileField, MultipleFileField, SelectMultipleField, DateField
from wtforms.validators import InputRequired, Email, Length, AnyOf
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_user import current_user, login_required, roles_required, UserManager, UserMixin
from flask_babelex import Babel
from flask_nav import Nav, register_renderer
from flask_nav.elements import *
from flask_bootstrap.nav import BootstrapRenderer
from flask_uploads import UploadSet, configure_uploads, IMAGES, TEXT, DOCUMENTS, DATA
from dominate import tags
import datetime
import json
import os
import smtplib
import ssl
from email.mime.text import MIMEText

app_name = '4D BIM'
projects = {}
software_names = ['Synchro Pro', 'Asta PowerProject', 'Navisworks Manage']


# Class-based application configuration
class ConfigClass(object):
    """ Flask application config """

    # Flask settings
    SECRET_KEY = 'Damien.Kavanagh.aec.services'

    # Flask-SQLAlchemy settings
    SQLALCHEMY_DATABASE_URI = 'sqlite:///users.sqlite'    # File-based SQL database
    SQLALCHEMY_TRACK_MODIFICATIONS = False    # Avoids SQLAlchemy warning

    # Flask-User settings
    USER_APP_NAME = app_name      # Shown in and email templates and page footers
    USER_ENABLE_EMAIL = False        # Disable email authentication
    USER_ENABLE_USERNAME = False    # Enable username authentication
    # USER_ENABLE_CONFIRM_EMAIL = False
    # USER_SEND_REGISTERED_EMAIL = False
    # USER_AFTER_REGISTER_ENDPOINT = 'user.login'
    USER_AFTER_LOGIN_ENDPOINT = 'recommend'

    USER_EMAIL_SENDER_NAME = USER_APP_NAME
    USER_EMAIL_SENDER_EMAIL = "noreply@example.com"

    UPLOADED_IMAGES_DEST = 'static/upload/img'
    UPLOADED_FILES_DEST = 'static/upload/file'


# Create Flask app load app.config
app = Flask(__name__)
app.config.from_object(__name__+'.ConfigClass')

# Initialize Flask-BabelEx
babel = Babel(app)

db = SQLAlchemy(app)


# Define the User data-model.
# NB: Make sure to add flask_user UserMixin !!!
class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    active = db.Column('is_active', db.Boolean(), nullable=False, server_default='1')

    # User authentication information. The collation='NOCASE' is required
    # to search case insensitively when USER_IFIND_MODE is 'nocase_collation'.
    email = db.Column(db.String(255, collation='NOCASE'), nullable=False, unique=True)
    email_confirmed_at = db.Column(db.DateTime())
    password = db.Column(db.String(255), nullable=False, server_default='')

    # User information
    first_name = db.Column(db.String(100, collation='NOCASE'), nullable=False, server_default='')
    last_name = db.Column(db.String(100, collation='NOCASE'), nullable=False, server_default='')

    # Define the relationship to Role via UserRoles
    roles = db.relationship('Role', secondary='user_roles')


# Define the Role data-model
class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(50), unique=True)


# Define the UserRoles association table
class UserRoles(db.Model):
    __tablename__ = 'user_roles'
    id = db.Column(db.Integer(), primary_key=True)
    user_id = db.Column(db.Integer(), db.ForeignKey('users.id', ondelete='CASCADE'))
    role_id = db.Column(db.Integer(), db.ForeignKey('roles.id', ondelete='CASCADE'))


# Setup Flask-User and specify the User data-model
user_manager = UserManager(app, db, User)

# Create all database tables
db.create_all()

# Create 'admin@example.com' user with 'Admin' and 'Agent' roles
if not User.query.filter(User.email == 'damien.kavanagh.aec.services@gmail.com').first():
    user = User(
        email='damien.kavanagh.aec.services@gmail.com',
        email_confirmed_at=datetime.datetime.utcnow(),
        password=user_manager.hash_password('adminpassword'),
        first_name='',
        last_name=''
    )
    user.roles.append(Role(name='Admin'))
    user.roles.append(Role(name='Expert'))
    db.session.add(user)
    db.session.commit()


def proximity(pA, pB):
    """
    INPUT: two project vectors pA and pB
    OUTPUT: a real number measuring the distance between
    them.
    NOTES: We can play around with different
    distance functions to see which is more suitable.
    """
    n = len(pA)
    return sum((1 - abs(a - b)) for a, b in zip(pA, pB)) / n


def nearest_neighbours(p, old_projects):
    """
    INPUT: p - a project vector, oldprojects - a list of tuples (project vector, software choice) [here software choice is a number in {1, 2, 3} representing the choice of software.
    OUTPUT: a list of the projects in oldprojects which most closely resemble
    our project of interest.
    NOTES: We can add a variable called threshold which controls the number of
    projects in our output - this could be either the maximum number of such projects, a ratio of the total number of projects, or a limit on the maximum distance.
    """
    threshold = 5
    return sorted(old_projects, key=lambda proj: proximity(p, proj[0]), reverse=True)[:threshold]


def software_choice2(p, old_projects):
    """
    INPUT: p - a project vector
    OUTPUT: a number in {0, 1, 2} indicating the project choice.
    NOTES:
    """
    scores = [0, 0, 0]

    for proj, soft in nearest_neighbours(p, old_projects):
        scores[soft - 1] = scores[soft - 1] + proximity(p, proj)

    return scores


def max_score(lst):
    ind, score = max(enumerate(lst), key=lambda x: x[1])
    return ind, score


def load_projects():
    global projects
    if os.path.exists(os.path.dirname(__file__) + '/projects.json'):
        with open(os.path.dirname(__file__) + '/projects.json', 'r') as fp:
            projects = json.load(fp)


def save_projects():
    global projects
    with open(os.path.dirname(__file__) + '/projects.json', 'w') as fp:
        json.dump(projects, fp)


def compare_list(a, b):
    if len(a) != len(b):
        return False
    length = len(a)
    return len([i for i in range(length) if a[i] == b[i]]) == length


class NoValidationSelectField(SelectField):
    def pre_validate(self, form):
        """per_validation is disabled"""


class NoValidationSelectMultipleField(SelectMultipleField):
    def pre_validate(self, form):
        """per_validation is disabled"""


class ProjectForm(FlaskForm):
    title = StringField('Project Title', validators=[InputRequired()])
    country = StringField('Country')
    city = StringField('City')
    local_authority = StringField('Local Authority')
    involvement = StringField('Individual Project Involvement', validators=[InputRequired()])
    date_of_project = DateField('Date of Project', id='date_of_project', format='%Y-%m-%d', validators=[InputRequired()])
    application = SelectField('4D Software Application Used', choices=[(ind, software_names[ind]) for ind in range(len(software_names))], coerce=int)
    version = StringField('Software Application Version', validators=[InputRequired()])
    email = StringField('E-mail', validators=[InputRequired(), Email(message='I don\'t like your email.')])

    def reset(self):
        blank_data = {'csrf': self.csrf_token}
        self.process(blank_data)


class ScoreForm(FlaskForm):
    title = StringField('Project Title', render_kw={'readonly': True})
    country = StringField('Country', render_kw={'readonly': True})
    city = StringField('City', render_kw={'readonly': True})
    local_authority = StringField('Local Authority', render_kw={'readonly': True})
    involvement = StringField('Individual Project Involvement', render_kw={'readonly': True})
    date_of_project = DateField('Date of Project', id='date_of_project', format='%Y-%m-%d', render_kw={'readonly': True})
    application = NoValidationSelectField('4D Software Application Used', choices=[(ind, software_names[ind]) for ind in range(len(software_names))], coerce=int, render_kw={'readonly': True, 'disabled': True})
    version = StringField('Software Application Version', render_kw={'readonly': True})
    email = StringField('E-mail', render_kw={'readonly': True})
    cm_restriction1 = SelectField('Beaurocracy', choices=[(0, 'Private'), (1, 'PPP'), (2, 'Public')], coerce=int)
    cm_restriction2 = SelectField('Site logistics', choices=[(0, 'Slightly Restricted'), (1, 'Restricted'), (2, 'Severely Restricted')], coerce=int)
    cm_restriction3 = SelectField('Resource planning', choices=[(0, 'Unlimited Resources'), (1, 'Moderate Resources'), (2, 'Limited Resources')], coerce=int)
    cm_restriction4 = SelectField('4D BIM knowledge', choices=[(0, 'High Level'), (1, 'Intermediate Level'), (2, 'Beginner Level')], coerce=int)
    cm_restriction5 = SelectField('Stakeholder involvement', choices=[(0, 'Very Influencial'), (1, 'Influencial'), (2, 'Little Influencial')], coerce=int)
    cm_restriction6 = SelectField('Transparency', choices=[(0, 'High Level Needed'), (1, 'Some Needed'), (2, 'Low Level Needed')], coerce=int)
    cm_restriction7 = SelectField('Return on Investment (ROI)', choices=[(0, 'Major Importance'), (1, 'Important'), (2, 'Not so Important')], coerce=int)
    cm_restriction8 = SelectField('Cost estimation', choices=[(0, 'Precise'), (1, 'Narrow Margin'), (2, 'Standard Margin')], coerce=int)
    cm_restriction9 = SelectField('Cost control', choices=[(0, 'Total'), (1, 'General'), (2, 'Minimal')], coerce=int)
    attribute1 = SelectField('Clash detection functionality', choices=[(x, str(x)) for x in range(11)], coerce=int)
    attribute2 = SelectField('Visualisation', choices=[(x, str(x)) for x in range(11)], coerce=int)
    attribute3 = SelectField('Discreet event simulation ', choices=[(x, str(x)) for x in range(11)], coerce=int)
    attribute4 = SelectField('Ease of use', choices=[(x, str(x)) for x in range(11)], coerce=int)
    attribute5 = SelectField('Collaboration funcionality', choices=[(x, str(x)) for x in range(11)], coerce=int)
    attribute6 = SelectField('Asset Management', choices=[(x, str(x)) for x in range(11)], coerce=int)
    attribute7 = SelectField('Payment structure (Lifecycle cost)', choices=[(x, str(x)) for x in range(11)], coerce=int)
    attribute8 = SelectField('Resource management', choices=[(x, str(x)) for x in range(11)], coerce=int)
    attribute9 = SelectField('Schedule vs actual WIP functionality', choices=[(x, str(x)) for x in range(11)], coerce=int)
    before_images = NoValidationSelectMultipleField('Image Files to remove', choices=[], coerce=int)
    images = MultipleFileField('New Image Files')
    before_files = NoValidationSelectMultipleField('Files to remove', choices=[], coerce=int)
    files = MultipleFileField('New Files')

    def reset(self):
        blank_data = {'csrf': self.csrf_token}
        self.process(blank_data)


class RecommendForm(FlaskForm):
    cm_restriction1 = SelectField('Beaurocracy', choices=[(0, 'Private'), (1, 'PPP'), (2, 'Public')], coerce=int)
    cm_restriction2 = SelectField('Site logistics', choices=[(0, 'Slightly Restricted'), (1, 'Restricted'), (2, 'Severely Restricted')], coerce=int)
    cm_restriction3 = SelectField('Resource planning', choices=[(0, 'Unlimited Resources'), (1, 'Moderate Resources'), (2, 'Limited Resources')], coerce=int)
    cm_restriction4 = SelectField('4D BIM knowledge', choices=[(0, 'High Level'), (1, 'Intermediate Level'), (2, 'Beginner Level')], coerce=int)
    cm_restriction5 = SelectField('Stakeholder involvement', choices=[(0, 'Very Influencial'), (1, 'Influencial'), (2, 'Little Influencial')], coerce=int)
    cm_restriction6 = SelectField('Transparency', choices=[(0, 'High Level Needed'), (1, 'Some Needed'), (2, 'Low Level Needed')], coerce=int)
    cm_restriction7 = SelectField('Return on Investment (ROI)', choices=[(0, 'Major Importance'), (1, 'Important'), (2, 'Not so Important')], coerce=int)
    cm_restriction8 = SelectField('Cost estimation', choices=[(0, 'Precise'), (1, 'Narrow Margin'), (2, 'Standard Margin')], coerce=int)
    cm_restriction9 = SelectField('Cost control', choices=[(0, 'Total'), (1, 'General'), (2, 'Minimal')], coerce=int)
    country = StringField('Country')
    city = StringField('City')
    local_authority = StringField('Local Authority')

    def reset(self):
        blank_data = {'csrf': self.csrf_token}
        self.process(blank_data)


class UserAdminForm(FlaskForm):
    email = StringField('E-mail')
    first_name = StringField('First Name')
    last_name = StringField('Last Name')
    roles = NoValidationSelectMultipleField('Roles', choices=[], coerce=int)

    def reset(self):
        blank_data = {'csrf': self.csrf_token}
        self.process(blank_data)


@app.route('/')
@app.route('/index')
def index():
    return render_template('index.html')


@app.route('/index_1')
def index_1():
    return render_template('index_1.html')


@app.route('/introduction')
def introduction():
    return render_template('introduction.html')


@app.route('/instruction')
def instruction():
    return render_template('instruction.html')


@app.route('/management')
def management():
    return render_template('management.html')


@app.route('/bim_tool')
def bim_tool():
    return render_template('bim_tool.html')


@app.route('/explained')
def explained():
    return render_template('explained.html')


@app.route('/constraints')
def constraints():
    return render_template('constraints.html')


@app.route('/attributes')
def attributes():
    return render_template('attributes.html')


@app.route('/planned_output')
def planned_output():
    return render_template('planned_output.html')


@app.route('/add', methods=['GET', 'POST'])
def add():
    form = ProjectForm()
    load_projects()
    if request.method == 'GET' and current_user.is_authenticated:
        form.email.data = current_user.email
    if request.method == 'POST' and form.validate_on_submit():
        max_id = 0
        if len(projects) != 0:
            max_id = max([int(x['id']) for x in projects.values()])
        projects[max_id+1] = {
            'id': str(max_id+1),
            'email': form.email.data,
            'title': form.title.data,
            'involvement': form.involvement.data,
            'application': form.application.data,
            'country': form.country.data,
            'city': form.city.data,
            'local_authority': form.local_authority.data,
            'version': form.version.data,
            'date_of_project': form.date_of_project.data.strftime('%Y-%m-%d'),
            'accepted': False,
            'history': False,
            'cm_restrictions': [0, 0, 0, 0, 0, 0, 0, 0, 0],
            'attribute_ratings': [0, 0, 0, 0, 0, 0, 0, 0, 0],
            'images': [],
            'files': []
        }
        save_projects()
        send_email("4dbimdecision@gmail.com", projects[max_id+1])

        form.reset()
        return render_template('add.html',
                               form=form,
                               info='Project successfully registered!')
    return render_template('add.html',
                           form=form,
                           info=None)


images = UploadSet('images', IMAGES)
files = UploadSet('files', TEXT + DOCUMENTS + DATA + tuple('csv ini json plist xml yaml yml'.split()) +
                  tuple('step dwf ifc igs iges man cv7 ipt iam ipj jt dgn prp prw x_b dri'.split()) +
                  tuple('rvm skp stl wrl wrz 3ds prjvwire f3d cam360 ipt prj sab rvt rfa rte'.split()) +
                  tuple('odbc html gbxm fli flc sp spx pp mpg avi gif bmp png jpg jpeg tif'.split()) +
                  tuple('mpp sp nwf nwd'.split()))
configure_uploads(app, [images, files])


@app.route('/score/<int:project_id>', methods=['GET', 'POST'])
@roles_required('Expert')
def score(project_id):
    if project_id == 0:
        project_id = None
    if project_id is not None:
        project_id = str(project_id)
        project_id = str(project_id)
    form = ScoreForm()
    load_projects()

    if request.method == 'GET':
        if project_id is not None:
            form.title.data = projects[project_id]['title']
            form.country.data = projects[project_id]['country']
            form.city.data = projects[project_id]['city']
            form.local_authority.data = projects[project_id]['local_authority']
            form.involvement.data = projects[project_id]['involvement']
            form.date_of_project.data = datetime.datetime.strptime(projects[project_id]['date_of_project'], "%Y-%m-%d").date()
            form.application.data = projects[project_id]['application']
            form.version.data = projects[project_id]['version']
            form.email.data = projects[project_id]['email']
            form.cm_restriction1.data = projects[project_id]['cm_restrictions'][0]
            form.cm_restriction2.data = projects[project_id]['cm_restrictions'][1]
            form.cm_restriction3.data = projects[project_id]['cm_restrictions'][2]
            form.cm_restriction4.data = projects[project_id]['cm_restrictions'][3]
            form.cm_restriction5.data = projects[project_id]['cm_restrictions'][4]
            form.cm_restriction6.data = projects[project_id]['cm_restrictions'][5]
            form.cm_restriction7.data = projects[project_id]['cm_restrictions'][6]
            form.cm_restriction8.data = projects[project_id]['cm_restrictions'][7]
            form.cm_restriction9.data = projects[project_id]['cm_restrictions'][8]
            form.attribute1.data = projects[project_id]['attribute_ratings'][0]
            form.attribute2.data = projects[project_id]['attribute_ratings'][1]
            form.attribute3.data = projects[project_id]['attribute_ratings'][2]
            form.attribute4.data = projects[project_id]['attribute_ratings'][3]
            form.attribute5.data = projects[project_id]['attribute_ratings'][4]
            form.attribute6.data = projects[project_id]['attribute_ratings'][5]
            form.attribute7.data = projects[project_id]['attribute_ratings'][6]
            form.attribute8.data = projects[project_id]['attribute_ratings'][7]
            form.attribute9.data = projects[project_id]['attribute_ratings'][8]
            form.before_images.choices = [(x, projects[project_id]['images'][x]) for x in range(len(projects[project_id]['images']))]
            form.before_files.choices = [(x, projects[project_id]['files'][x]) for x in range(len(projects[project_id]['files']))]
            if projects[project_id]['history']:
                form.cm_restriction1.render_kw = {'readonly': True, 'disabled': True}
                form.cm_restriction2.render_kw = {'readonly': True, 'disabled': True}
                form.cm_restriction3.render_kw = {'readonly': True, 'disabled': True}
                form.cm_restriction4.render_kw = {'readonly': True, 'disabled': True}
                form.cm_restriction5.render_kw = {'readonly': True, 'disabled': True}
                form.cm_restriction6.render_kw = {'readonly': True, 'disabled': True}
                form.cm_restriction7.render_kw = {'readonly': True, 'disabled': True}
                form.cm_restriction8.render_kw = {'readonly': True, 'disabled': True}
                form.cm_restriction9.render_kw = {'readonly': True, 'disabled': True}
                form.attribute1.render_kw = {'readonly': True, 'disabled': True}
                form.attribute2.render_kw = {'readonly': True, 'disabled': True}
                form.attribute3.render_kw = {'readonly': True, 'disabled': True}
                form.attribute4.render_kw = {'readonly': True, 'disabled': True}
                form.attribute5.render_kw = {'readonly': True, 'disabled': True}
                form.attribute6.render_kw = {'readonly': True, 'disabled': True}
                form.attribute7.render_kw = {'readonly': True, 'disabled': True}
                form.attribute8.render_kw = {'readonly': True, 'disabled': True}
                form.attribute9.render_kw = {'readonly': True, 'disabled': True}
    if request.method == 'POST' and form.validate_on_submit():
        projects[project_id].update({
            'cm_restrictions': [form.cm_restriction1.data,
                                form.cm_restriction2.data,
                                form.cm_restriction3.data,
                                form.cm_restriction4.data,
                                form.cm_restriction5.data,
                                form.cm_restriction6.data,
                                form.cm_restriction7.data,
                                form.cm_restriction8.data,
                                form.cm_restriction9.data],
            'attribute_ratings': [form.attribute1.data,
                                  form.attribute2.data,
                                  form.attribute3.data,
                                  form.attribute4.data,
                                  form.attribute5.data,
                                  form.attribute6.data,
                                  form.attribute7.data,
                                  form.attribute8.data,
                                  form.attribute9.data]
        })
        form.before_images.choices = [(x, projects[project_id]['images'][x]) for x in range(len(projects[project_id]['images']))]
        form.before_files.choices = [(x, projects[project_id]['files'][x]) for x in range(len(projects[project_id]['files']))]

        for ind in form.before_images.data[::-1]:
            os.remove('static/upload/img/'+projects[project_id]['images'][ind])
            del projects[project_id]['images'][ind]

        filenames = []
        for item in request.files.getlist('images'):
            filenames.append(images.save(item))
        projects[project_id]['images'] += filenames

        for ind in form.before_files.data[::-1]:
            os.remove('static/upload/file/'+projects[project_id]['files'][ind])
            del projects[project_id]['files'][ind]

        filenames = []
        for item in request.files.getlist('files'):
            filenames.append(files.save(item))
        projects[project_id]['files'] += filenames

        save_projects()
        return render_template('score.html',
                               form=form,
                               info='Scores successfully updated!',
                               projects=[x for x in projects.values() if x['accepted'] and x['email'] == current_user.email],
                               images=None if project_id is None else projects[project_id]['images'],
                               files=None if project_id is None else projects[project_id]['files'],
                               project_id=project_id)
    return render_template('score.html',
                           form=form, info=None,
                           projects=[x for x in projects.values() if x['accepted'] and x['email'] == current_user.email],
                           images=None if project_id is None else projects[project_id]['images'],
                           files=None if project_id is None else projects[project_id]['files'],
                           project_id=project_id)


@app.route('/recommend', methods=['GET', 'POST'])
def recommend():
    form = RecommendForm()
    load_projects()

    if request.method == 'POST' and form.validate_on_submit():
        project = {
            'cm_restrictions': [form.cm_restriction1.data,
                                form.cm_restriction2.data,
                                form.cm_restriction3.data,
                                form.cm_restriction4.data,
                                form.cm_restriction5.data,
                                form.cm_restriction6.data,
                                form.cm_restriction7.data,
                                form.cm_restriction8.data,
                                form.cm_restriction9.data]
        }
        # soft_num, soft_score = max_score(software_choice2(project['cm_restrictions'],
        #                                                   [(x['cm_restrictions'], x['application']) for x in projects.values() if x['history']]))

        prjs = [x for x in projects.values() if x['history'] and compare_list(x['cm_restrictions'], project['cm_restrictions'])]
        return render_template('recommend.html',
                               form=form,
                               info='Scores successfully updated!',
                               projects=None if len(prjs) == 0 else prjs,
                               project=project,
                               software_names=software_names)
    return render_template('recommend.html',
                           form=form, info=None,
                           projects=[],
                           project=None,
                           software_names=software_names)


@app.route('/accept/<int:project_id>', methods=['GET', 'POST'])
@roles_required('Admin')
def accept(project_id):
    if project_id == 0:
        project_id = None
    if project_id is not None:
        project_id = str(project_id)
    form = ScoreForm()
    form.cm_restriction1.render_kw = {'readonly': True, 'disabled': True}
    form.cm_restriction2.render_kw = {'readonly': True, 'disabled': True}
    form.cm_restriction3.render_kw = {'readonly': True, 'disabled': True}
    form.cm_restriction4.render_kw = {'readonly': True, 'disabled': True}
    form.cm_restriction5.render_kw = {'readonly': True, 'disabled': True}
    form.cm_restriction6.render_kw = {'readonly': True, 'disabled': True}
    form.cm_restriction7.render_kw = {'readonly': True, 'disabled': True}
    form.cm_restriction8.render_kw = {'readonly': True, 'disabled': True}
    form.cm_restriction9.render_kw = {'readonly': True, 'disabled': True}
    form.attribute1.render_kw = {'readonly': True, 'disabled': True}
    form.attribute2.render_kw = {'readonly': True, 'disabled': True}
    form.attribute3.render_kw = {'readonly': True, 'disabled': True}
    form.attribute4.render_kw = {'readonly': True, 'disabled': True}
    form.attribute5.render_kw = {'readonly': True, 'disabled': True}
    form.attribute6.render_kw = {'readonly': True, 'disabled': True}
    form.attribute7.render_kw = {'readonly': True, 'disabled': True}
    form.attribute8.render_kw = {'readonly': True, 'disabled': True}
    form.attribute9.render_kw = {'readonly': True, 'disabled': True}
    load_projects()
    if request.method == 'GET':
        if project_id is not None:
            form.title.data = projects[project_id]['title']
            form.country.data = projects[project_id]['country']
            form.city.data = projects[project_id]['city']
            form.local_authority.data = projects[project_id]['local_authority']
            form.involvement.data = projects[project_id]['involvement']
            form.date_of_project.data = datetime.datetime.strptime(projects[project_id]['date_of_project'], "%Y-%m-%d").date()
            form.application.data = projects[project_id]['application']
            form.version.data = projects[project_id]['version']
            form.email.data = projects[project_id]['email']
            form.cm_restriction1.data = projects[project_id]['cm_restrictions'][0]
            form.cm_restriction2.data = projects[project_id]['cm_restrictions'][1]
            form.cm_restriction3.data = projects[project_id]['cm_restrictions'][2]
            form.cm_restriction4.data = projects[project_id]['cm_restrictions'][3]
            form.cm_restriction5.data = projects[project_id]['cm_restrictions'][4]
            form.cm_restriction6.data = projects[project_id]['cm_restrictions'][5]
            form.cm_restriction7.data = projects[project_id]['cm_restrictions'][6]
            form.cm_restriction8.data = projects[project_id]['cm_restrictions'][7]
            form.cm_restriction9.data = projects[project_id]['cm_restrictions'][8]
            form.attribute1.data = projects[project_id]['attribute_ratings'][0]
            form.attribute2.data = projects[project_id]['attribute_ratings'][1]
            form.attribute3.data = projects[project_id]['attribute_ratings'][2]
            form.attribute4.data = projects[project_id]['attribute_ratings'][3]
            form.attribute5.data = projects[project_id]['attribute_ratings'][4]
            form.attribute6.data = projects[project_id]['attribute_ratings'][5]
            form.attribute7.data = projects[project_id]['attribute_ratings'][6]
            form.attribute8.data = projects[project_id]['attribute_ratings'][7]
            form.attribute9.data = projects[project_id]['attribute_ratings'][8]
            form.before_images.choices = [(x, projects[project_id]['images'][x]) for x in range(len(projects[project_id]['images']))]
            form.before_files.choices = [(x, projects[project_id]['files'][x]) for x in range(len(projects[project_id]['files']))]
    if request.method == 'POST' and form.validate_on_submit():

        form.before_images.choices = [(x, projects[project_id]['images'][x]) for x in range(len(projects[project_id]['images']))]
        form.before_files.choices = [(x, projects[project_id]['files'][x]) for x in range(len(projects[project_id]['files']))]

        for ind in form.before_images.data[::-1]:
            os.remove('static/upload/img/'+projects[project_id]['images'][ind])
            del projects[project_id]['images'][ind]

        filenames = []
        for item in request.files.getlist('images'):
            filenames.append(images.save(item))
        projects[project_id]['images'] += filenames

        for ind in form.before_files.data[::-1]:
            os.remove('static/upload/file/'+projects[project_id]['files'][ind])
            del projects[project_id]['files'][ind]

        filenames = []
        for item in request.files.getlist('files'):
            filenames.append(files.save(item))
        projects[project_id]['files'] += filenames

        save_projects()
        return render_template('accept.html',
                               form=form,
                               info='Project data successfully updated!',
                               projects=list(projects.values()),
                               project_id=project_id,
                               images=None if project_id is None else projects[project_id]['images'],
                               files=None if project_id is None else projects[project_id]['files'],
                               accepted=True if project_id is None else projects[project_id]['accepted'],
                               history=True if project_id is None else projects[project_id]['history'])
    return render_template('accept.html',
                           form=form, info=None,
                           projects=list(projects.values()),
                           project_id=project_id,
                           images=None if project_id is None else projects[project_id]['images'],
                           files=None if project_id is None else projects[project_id]['files'],
                           accepted=True if project_id is None else projects[project_id]['accepted'],
                           history=True if project_id is None else projects[project_id]['history'])


@app.route('/accept/accept/<int:project_id>')
@roles_required('Admin')
def accept_project(project_id):
    load_projects()
    project_id = str(project_id)
    projects[project_id]['accepted'] = True
    save_projects()
    return redirect(url_for('accept', project_id=0))


@app.route('/accept/addhistory/<int:project_id>')
@roles_required('Admin')
def add_history_project(project_id):
    load_projects()
    project_id = str(project_id)
    projects[project_id]['history'] = True
    save_projects()
    return redirect(url_for('accept', project_id=0))


@app.route('/accept/removehistory/<int:project_id>')
@roles_required('Admin')
def remove_history_project(project_id):
    load_projects()
    project_id = str(project_id)
    projects[project_id]['history'] = False
    save_projects()
    return redirect(url_for('accept', project_id=0))


@app.route('/accept/del/<int:project_id>')
@roles_required('Admin')
def delete_project(project_id):
    load_projects()
    project_id = str(project_id)
    del projects[project_id]
    save_projects()
    return redirect(url_for('accept', project_id=0))


@app.route('/useradmin/<int:user_id>', methods=['GET', 'POST'])
@roles_required('Admin')
def useradmin(user_id):
    if user_id == 0:
        user_id = None
    form = UserAdminForm()

    users = User.query.all()
    roles = Role.query.all()

    if request.method == 'GET':
        if user_id is not None and len([x for x in users if x.id == user_id]) > 0:
            user = [x for x in users if x.id == user_id][0]
            form.email.data = user.email
            form.first_name.data = user.first_name
            form.last_name.data = user.last_name
            form.roles.choices = [(x.id, x.name) for x in roles]
            form.roles.data = [x.id for x in user.roles]
    if request.method == 'POST' and form.validate_on_submit():
        user = [x for x in users if x.id == user_id][0]
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        user.roles = [x for x in roles if x.id in form.roles.data]
        db.session.commit()

        form.roles.choices = [(x.id, x.name) for x in roles]
        form.roles.data = [x.id for x in user.roles]

        return render_template('useradmin.html',
                               form=form,
                               info='Scores successfully updated!',
                               users=users,
                               user_id=user_id)
    return render_template('useradmin.html',
                           form=form, info=None,
                           users=users,
                           user_id=user_id)


@app.route('/useradmin/add', methods=['POST'])
@roles_required('Admin')
def add_user():
    form = UserAdminForm()
    if request.method == 'POST' and form.validate_on_submit():
        users = User.query.all()
        if len([x for x in users if x.email == form.email.data]) == 0:
            roles = Role.query.all()
            user = User(
                email=form.email.data,
                email_confirmed_at=datetime.datetime.utcnow(),
                password=user_manager.hash_password('123456'),
                first_name=form.first_name.data,
                last_name=form.last_name.data
            )
            for role in [x for x in roles if x.id in form.roles.data]:
                user.roles.append(role)
            db.session.add(user)
            db.session.commit()

    return redirect(url_for('useradmin', user_id=0))


@app.route('/useradmin/del/<int:user_id>')
@roles_required('Admin')
def delete_user(user_id):
    user = User.query.get(user_id)
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('useradmin', project_id=0))


nav = Nav()


@nav.navigation()
def mynavbar():
    items = [View(app_name, 'index'),
             Subgroup('Website Design',
                      View('Introduction', 'introduction'),
                      View('Design', 'instruction')),
             Subgroup('Successful Construction Management and 4D BIM',
                      View('Improving Construction Management with 4D BIM', 'management')),
             Subgroup('Best Practice 4D BIM',
                      View('Best Practice Evaluation', 'bim_tool'),
                      View('Explained', 'explained'),
                      View('Project Constraints', 'constraints'),
                      View('4D BIM Attributes', 'attributes'),
                      View('Planned Outputs', 'planned_output'))]
    # items = [View(app_name, 'index'),
    #          View('Recommendation', 'recommend')]
    if current_user.is_authenticated:
        is_expert = len([role for role in current_user.roles if role.name == 'Expert']) > 0
        is_admin = len([role for role in current_user.roles if role.name == 'Admin']) > 0
        if is_expert and is_admin:
            items.append(Subgroup('Decision Support System',
                                  View('Recommendation', 'recommend'),
                                  View('Add Project', 'add'),
                                  View('Score Projects', 'score', project_id=0),
                                  View('Manage Projects', 'accept', project_id=0),
                                  View('Manage Users', 'useradmin', user_id=0)))
        elif is_expert:
            items.append(Subgroup('Decision Support System',
                                  View('Recommendation', 'recommend'),
                                  View('Add Project', 'add'),
                                  View('Score Projects', 'score', project_id=0)))
        elif is_admin:
            items.append(Subgroup('Decision Support System',
                                  View('Recommendation', 'recommend'),
                                  View('Add Project', 'add'),
                                  View('Manage Projects', 'accept', project_id=0),
                                  View('Manage Users', 'useradmin', user_id=0)))
        name = current_user.first_name + ' ' + current_user.last_name
        if name == ' ':
            name = 'User'
        items.append(Subgroup(name,
                              View('Edit Profile', 'user.edit_user_profile'),
                              View('Logout', 'user.logout')))
    else:
        items.append(Subgroup('Decision Support System',
                              View('Recommendation', 'recommend'),
                              View('Add Project', 'add')))
        items.append(Subgroup('Administration',
                              View('Login', 'user.login')))

    return Navbar(*items)


nav.init_app(app)


@nav.renderer()
class InvertedRenderer(BootstrapRenderer):
    def visit_Navbar(self, node):
        root = super(InvertedRenderer, self).visit_Navbar(node)
        root['class'] = 'navbar navbar-inverse'
        return root


register_renderer(app, 'inverted', InvertedRenderer)

Bootstrap(app)


def send_email(receiver_email, project):
    port = 465  # For SSL
    smtp_server = "smtp.gmail.com"
    sender_email = "damien.kavanagh.aec.services@gmail.com"  # Enter your address
    password = "11Munster"

    message = """Project Title: %s
Country: %s
City: %s
Local Authority: %s
Individual Project Involvement: %s
Date of Project: %s
4D Software Application Used: %s
Software Application Version: %s
E-mail: %s"""

    server = smtplib.SMTP_SSL(smtp_server, port)
    server.login(sender_email, password)

    msg = MIMEText(message % (project['title'],
                              project['country'],
                              project['city'],
                              project['local_authority'],
                              project['involvement'],
                              project['date_of_project'],
                              software_names[project['application']],
                              project['version'],
                              project['email']))
    msg['Subject'] = "New 4D BIM Project"
    msg['From'] = "4dbimdecisions.com"
    msg['To'] = receiver_email

    server.sendmail(sender_email, receiver_email, msg.as_string())


if __name__ == '__main__':
    app.run()
