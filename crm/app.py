from flask import Flask, flash, redirect, render_template, url_for, request
from flask_sqlalchemy import SQLAlchemy
import datetime as dt
from datetime import date
from datetime import timedelta
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms import Form, BooleanField, StringField, PasswordField, validators
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///services-crm.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


EVENT_COLORS = {
    "Light Purple": 1,
    "Light Green": 2,
    "Purple": 3,
    "Pink": 4,
    "Yellow": 5,
    "Orange": 6,
    "Light Blue": 7,
    "Grey": 8,
    "Dark Blue": 9,
    "Dark Green": 10,
    "Red": 11
}


class PtClients(db.Model):
    __tablename__ = 'pt clients'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String, nullable=False)
    last_name = db.Column(db.String)
    gender = db.Column(db.String, nullable=False)
    date_of_birth = db.Column(db.String)
    age = db.Column(db.String)
    email = db.Column(db.String, nullable=False)
    phone_number = db.Column(db.Unicode(44), nullable=False)
    client_goals = db.Column(db.String, nullable=False)
    is_client = db.Column(db.String, nullable=False)
    start_date = db.Column(db.String)
    weeks_coached = db.Column(db.Integer)
    client_notes = db.Column(db.String, nullable=False)
    creator = db.Column(db.String, nullable=False)

    def __repr__(self):
        return f'<Client {self.first_name}>'


class EventInfo(db.Model):
    __tablename__ = "event type"
    id = db.Column(db.Integer, primary_key=True)
    event_summary = db.Column(db.String, nullable=False)
    description = db.Column(db.String)
    location = db.Column(db.String)
    color = db.Column(db.Integer)
    recurring = db.Column(db.String)
    duration = db.Column(db.String, nullable=False)
    appointment_use = db.Column(db.Integer, nullable=False)
    creator = db.Column(db.String, nullable=False)

    def __repr__(self):
        return f'<Event {self.event_summary}>'


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String, nullable=False)
    last_name = db.Column(db.String, nullable=False)
    business_name = db.Column(db.String)
    email = db.Column(db.String, nullable=False)
    password = db.Column(db.String, nullable=False)
    remember_me = db.Column(db.Boolean)
    token_json = db.Column(db.JSON)
    user_id = db.Column(db.String)


with app.app_context():
    db.create_all()

now = int(dt.datetime.now().strftime("%Y%m%d"))


class RegistrationForm(Form):
    first_name = StringField('First Name', [validators.Length(min=2, max=25)],
                             render_kw={"placeholder": "Enter First Name"})
    last_name = StringField('Last Name', [validators.Length(min=2, max=25)],
                            render_kw={"placeholder": "Enter Last Name"})
    email = StringField('Email Address', [validators.Length(min=6, max=35)], render_kw={"placeholder": "Enter Email"})
    business_name = StringField('Business Name', [validators.Length(min=6, max=35)],
                                render_kw={"placeholder": "Enter Business Name"})
    password = PasswordField('New Password', [
        validators.DataRequired(),
        validators.EqualTo("confirm", message='Passwords must match')], render_kw={"placeholder": "Enter Password"})
    confirm = PasswordField('Repeat Password', [validators.EqualTo("password", "Passwords must match")],
                            render_kw={"placeholder": "Repeat Password"})
    remember_me = BooleanField('Remember me')


class LoginForm(Form):
    email = StringField('Email Address', [validators.Length(min=6, max=35)], render_kw={"placeholder": "Enter Email"})
    password = PasswordField('New Password', [validators.DataRequired()], render_kw={"placeholder": "Enter Password"})


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def age(client_dob):
    today1 = int(dt.datetime.now().strftime("%d"))
    month1 = int(dt.datetime.now().strftime("%m"))
    year1 = int(dt.datetime.now().strftime("%Y"))
    date1 = date(year1, month1, today1)
    client_dob = client_dob.replace("-", "")
    day2 = int(client_dob[6:])
    month2 = int(client_dob[4:6])
    year2 = int(client_dob[:4])
    date2 = date(year2, month2, day2)
    age = int(abs(date2 - date1).days // 365)
    return age


def weeks_coached(start_date):
    today1 = int(dt.datetime.now().strftime("%d"))
    month1 = int(dt.datetime.now().strftime("%m"))
    year1 = int(dt.datetime.now().strftime("%Y"))
    date1 = date(year1, month1, today1)
    start_date = start_date.replace("-", "")
    if start_date < dt.datetime.now().strftime("Y-%m-%d"):
        return -1
    day2 = int(start_date[6:])
    month2 = int(start_date[4:6])
    year2 = int(start_date[:4])
    date2 = date(year2, month2, day2)
    weeks = int(abs(date2 - date1).days // 7)
    return weeks


def create_event_id(title, user_id):
    new_id = user_id.replace(" ", "").replace("w", "").replace("x", "").replace("y", "").replace("z", "").replace("$",
                                                                                                                  "").lower()
    new_id = title.replace(" ", "").replace("w", "").replace("x", "").replace("y", "").replace("z", "").replace("$",
                                                                                                                "").lower() + new_id
    return new_id


SCOPES = ['https://www.googleapis.com/auth/calendar']


def find_all_calls(results=0):
    """find all results in a calendar. if the event has the relevant id, it will add it to a dict to be used later.
    results kwarg is for how many things to pull from users calendar
    """
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials2.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('calendar', 'v3', credentials=creds)

        now = dt.datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(calendarId='primary', timeMin=now,
                                              maxResults=results, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])

        if not events:
            print('No upcoming events found.')
            return

        event_summary = []
        for event in events:
            event_id = event["id"]
            user = current_user.user_id.replace(" ", "").replace("w", "").replace("x", "").replace("y", "").replace("$",
                                                                                                                    "").replace(
                "z", "").lower()
            if user[-10:] == event_id[-10:]:
                start = dt.datetime.strptime(event['start'].get('dateTime', event['start'].get('date'))[:16],
                                             "%Y-%m-%dT%H:%M")
                end = dt.datetime.strptime(event['end'].get('dateTime', event['end'].get('date'))[:16],
                                           "%Y-%m-%dT%H:%M")
                duration = end - start
                duration = str(duration)

                try:
                    if int(duration[:2]) > 10:
                        duration = duration[:5]
                        hours = duration[:2] + "hrs"
                        mins = duration[3:5] + "mins"
                        duration = f"{hours} {mins}"
                except ValueError:
                    if duration[:1] == "0":
                        duration = duration[2:4] + " mins"
                    elif int(duration[:1]) < 10:
                        duration = duration[:4]
                        if duration[:1] != "1":
                            hours = duration[:1] + "hrs"
                        else:
                            hours = duration[:1] + " hour"
                        if duration[2:4] != "00":
                            mins = duration[2:4] + "mins"
                            duration = f"{hours} {mins}"
                        else:
                            duration = hours

                summary_words = event["summary"].split(" ")
                title = ""

                for word in summary_words[:-2]:
                    title += word + " "

                event_dict = {"first_name": summary_words[-2],
                              "last_name": summary_words[-1],
                              "summary": title,
                              "start_date": dt.datetime.strftime(start, "%m/%d"),
                              "start_time": dt.datetime.strftime(start, "%Y-%m-%dT%H:%M")[11:16],
                              "end_time": dt.datetime.strftime(end, "%Y-%m-%dT%H:%M")[11:16],
                              "duration": duration,
                              "phone_number": event["attendees"][0],
                              "email": event["attendees"][0]["email"],
                              "id": event["id"]
                              }
                event_summary.append(event_dict)
        return event_summary

    except HttpError as error:
        print('An error occurred: %s' % error)


def add_event(title="", name="", location="", description="", date_time="", duration="", attendees="", color="",
              phone_number=None, event_id=""):
    """adds event to a calendar based on input.
    """

    time_obj = dt.datetime.strptime(date_time, "%Y-%m-%dT%H:%M")
    end_time = dt.datetime.strftime((time_obj + timedelta(minutes=int(duration))), "%H:%M")
    start_time = dt.datetime.strftime(time_obj, "%H:%M")
    day = dt.datetime.strftime(time_obj, "%Y-%m-%d")

    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials2.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('calendar', 'v3', credentials=creds)
        event = {
            "summary": f"{title} {name}",
            "location": location,
            "description": description,
            "colorId": color,
            "status": "confirmed",
            "id": event_id,
            "start": {
                "dateTime": f"{day}T{start_time}:00",
                "timeZone": "GMT+01:00"
            },
            "end": {
                "dateTime": f"{day}T{end_time}:00",
                "timeZone": "GMT+01:00"
            },
            "attendees": [
                {"email": attendees,
                 "comment": phone_number
                 }
            ]
        }

        service.events().insert(calendarId="primary", body=event).execute()

        # print(f"Event created {event.get('htmlLink')}") prints event link

    except HttpError as error:
        print(error)
    #     print('An error occurred: %s' % error)


@app.route("/", methods=["POST", "GET"])
def landing():
    register_form = RegistrationForm(request.form)
    login_form = LoginForm(request.form)
    if request.method == "POST":
        form_type = request.form["btn"]
        if form_type == "signup":
            user = User.query.filter_by(email=request.form.get('email')).first()
            if user:
                flash("You've already signed up with that email, log in instead.")
                return redirect(url_for('landing'))
            elif not register_form.validate():
                flash("Oops, some of the information your entered wasn't valid. Please try again")
                return render_template("landing.html")
            elif register_form.validate():
                new_user = User(first_name=request.form.get("first_name"),
                                last_name=request.form.get("last_name"),
                                email=register_form.email.data,
                                password=generate_password_hash(password=register_form.password.data,
                                                                method='pbkdf2:sha256',
                                                                salt_length=10),
                                remember_me=register_form.remember_me.data,
                                business_name=register_form.business_name.data,
                                user_id=generate_password_hash(password=register_form.last_name.data,
                                                               method='pbkdf2:sha256',
                                                               salt_length=2).replace("pbkdf2:sha256:600000$", ""))
                with app.app_context():
                    db.session.add(new_user)
                    db.session.commit()
                    flash("Welcome! You've successfully created your account.")
                    login_user(new_user, remember=True)
            return redirect(url_for("home"))

        # login function
        if form_type == "login":
            email = request.form.get('email')
            password = request.form.get('password')

            user = User.query.filter_by(email=email).first()
            if not user:
                flash("That email does not exist, please try again or create a new account.")
            elif not check_password_hash(user.password, password):
                flash('Password incorrect, please try again.')
            else:
                login_user(user, remember=True)
                return redirect(url_for("home"))
    return render_template("landing.html", register_form=register_form, login_form=login_form)


@app.route("/home")
@login_required
def home():
    return render_template("index.html")


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('landing'))


@app.route("/add-client", methods=["GET", "POST"])
@login_required
def add_client():
    if request.method == "POST":
        new_client = PtClients(first_name=request.form["first_name"],
                               last_name=request.form["last_name"],
                               gender=request.form["GenderRadio"],
                               date_of_birth=request.form["date_of_birth"],
                               age=age(request.form["date_of_birth"]),
                               email=request.form["email"],
                               phone_number=request.form["phone_number"],
                               client_goals=request.form["client-goals"],
                               is_client=request.form["listGroupRadios"],
                               start_date=request.form["start_date"],
                               weeks_coached=weeks_coached(request.form["start_date"]),
                               client_notes=request.form["client_notes"],
                               creator=current_user.user_id)
        with app.app_context():
            db.session.add(new_client)
            db.session.commit()
        return redirect(url_for("all_clients"))
    return render_template("add.html")


@app.route("/all-clients", methods=["GET", "POST"])
@login_required
def all_clients():
    if request.method == "POST":
        if request.form["client_type"] == "active_clients":
            active_clients = db.session.execute(
                db.select(PtClients).filter_by(is_client="Current Client", creator=current_user.user_id)).scalars()
            return render_template("all_clients.html", all_pt_clients=active_clients)
        elif request.form["client_type"] == "paused_clients":
            paused_clients = db.session.execute(
                db.select(PtClients).filter_by(is_client="Paused Client", creator=current_user.user_id)).scalars()
            return render_template("all_clients.html", all_pt_clients=paused_clients)
        elif request.form["client_type"] == "old_clients":
            old_clients = db.session.execute(
                db.select(PtClients).filter_by(is_client="Old Client", creator=current_user.user_id)).scalars()
            return render_template("all_clients.html", all_pt_clients=old_clients)
        elif request.form["client_type"] == "starting_soon":
            pending_clients = db.session.execute(
                db.select(PtClients).filter_by(is_client="Starting Soon", creator=current_user.user_id)).scalars()
            return render_template("all_clients.html", all_pt_clients=pending_clients)
    all_pt_clients = db.session.execute(db.select(PtClients).filter_by(creator=current_user.user_id)).scalars()
    return render_template("all_clients.html", all_pt_clients=all_pt_clients)


@app.route("/client-profile/<first_name>/<last_name>/<id>", methods=["POST", "GET"])
def client_profile(first_name, last_name, id):
    client_id = id
    selected_client = PtClients.query.filter_by(id=id)
    client_to_update = db.session.execute(db.select(PtClients).filter_by(id=id)).scalar()
    if request.method == "POST":
        form_type = request.form["btn"]
        if form_type == "delete":
            client_to_delete = db.session.get(PtClients, client_id)
            db.session.delete(client_to_delete)
            db.session.commit()
            return redirect(url_for("all_clients"))
        elif form_type == "update_notes":
            client_to_update.client_notes = request.form["client_notes"]
            db.session.commit()
        elif form_type == "new_dob":
            if request.form["date_of_birth"] == "":
                return render_template("client-profile.html", selected_client=selected_client)
            new_age = age(request.form["date_of_birth"])
            client_to_update.date_of_birth = request.form["date_of_birth"]
            client_to_update.age = new_age
            db.session.commit()
            return render_template("client-profile.html", selected_client=selected_client)
        elif form_type == "new_gender":
            if request.form["GenderRadio"] == "":
                return render_template("client-profile.html", selected_client=selected_client)
            client_to_update.gender = request.form["GenderRadio"]
            db.session.commit()
        elif form_type == "updated_email":
            if request.form["new_email"] == "":
                return render_template("client-profile.html", selected_client=selected_client)
            client_to_update.email = request.form["new_email"]
            db.session.commit()
        elif form_type == "updated_number":
            if request.form["new_number"] == "":
                return render_template("client-profile.html", selected_client=selected_client)
            client_to_update.phone_number = request.form["new_number"]
            db.session.commit()
            return render_template("client-profile.html", selected_client=selected_client)
        elif form_type == "updated_goals":
            if request.form["new_goals"] == "":
                return render_template("client-profile.html", selected_client=selected_client)
            client_to_update.client_goals = request.form["new_goals"]
            db.session.commit()
            return render_template("client-profile.html", selected_client=selected_client)
        elif form_type == "new_status":
            if request.form["StatusRadio"] == "":
                return render_template("client-profile.html", selected_client=selected_client)
            client_to_update.is_client = request.form["StatusRadio"]
            db.session.commit()
            return render_template("client-profile.html", selected_client=selected_client)
        elif form_type == "updated_name":
            if request.form["new_first_name"] == "" or request.form["new_last_name"] == "":
                return render_template("client-profile.html", selected_client=selected_client)
            client_to_update.first_name = request.form["new_first_name"]
            client_to_update.last_name = request.form["new_last_name"]
            db.session.commit()
            return render_template("client-profile.html", selected_client=selected_client)
    return render_template("client-profile.html", selected_client=selected_client)


@app.route("/all-events", methods=["GET", "POST"])
@login_required
def all_bookings():
    event_summary = find_all_calls(results=10)
    return render_template("all_bookings.html", event_summary=event_summary)


@app.route("/book-call/<template>", methods=["GET", "post"])
@login_required
def book_call(template):
    client_chosen = False
    all_clients = db.session.execute(db.select(PtClients).filter_by(creator=current_user.user_id)).scalars()
    if template == "no-template":
        return redirect(url_for("no_template_booking"))
    else:
        selected_event = db.session.execute(db.select(EventInfo).filter_by(event_summary=template)).scalar()
        template_color = ""
        for color in EVENT_COLORS:
            if EVENT_COLORS[color] == selected_event.color:
                template_color = color
        if request.method == "POST":
            form_type = request.form["btn2"]
            if form_type == "book_call":
                add_event(title=request.form["title"],
                          name=request.form['name'],
                          description=request.form['appointment_description'],
                          date_time=request.form["meeting-time"],
                          duration=request.form["meeting-duration"],
                          location=request.form["appointment_location"],
                          color=selected_event.color,
                          event_id=create_event_id(
                              generate_password_hash(password=request.form["title"], method='pbkdf2:sha256',
                                                     salt_length=2).replace("pbkdf2:sha256:600000$", ""),
                              current_user.user_id),
                          attendees=request.form["attendees_email"],
                          phone_number=request.form["attendees_phone_number"])
                selected_event.appointment_use += 1
                db.session.commit()
                return redirect(url_for("all_bookings"))
            elif form_type == "add_client":
                client_chosen = True
                selected_client = db.session.execute(
                    db.select(PtClients).filter_by(first_name=request.form["client_search"].split()[0],
                                                   last_name=request.form["client_search"].split()[1])).scalar()
                return render_template("book_call.html", all_clients=all_clients, client_chosen=client_chosen,
                                       selected_client=selected_client, selected_event=selected_event,
                                       color=template_color)
        return render_template("book_call.html", all_clients=all_clients, client_chosen=client_chosen,
                               selected_event=selected_event, color=template_color)


@app.route("/book-event/no-template", methods=["POST", "GET"])
@login_required
def no_template_booking():
    all_clients = db.session.execute(db.select(PtClients).filter_by(creator=current_user.user_id)).scalars()
    client_chosen = False
    if request.method == "POST":
        form_type = request.form["btn2"]
        if form_type == "book_call":
            add_event(title=request.form['title'],
                      name=request.form['name'],
                      description=request.form['appointment_description'],
                      location=request.form["appointment_location"],
                      date_time=request.form["meeting-time"],
                      duration=request.form["meeting-duration"],
                      color=EVENT_COLORS.get(request.form["event_color"]),
                      event_id=create_event_id(
                          generate_password_hash(password=request.form["title"], method='pbkdf2:sha256',
                                                 salt_length=2).replace("pbkdf2:sha256:600000$", ""),
                          current_user.user_id),
                      attendees=request.form["attendees_email"],
                      phone_number=request.form["attendees_phone_number"])
            return redirect(url_for("all_bookings"))
        elif form_type == "add_client":
            client_chosen = True
            selected_client = db.session.execute(
                db.select(PtClients).filter_by(first_name=request.form["client_search"].split()[0],
                                               last_name=request.form["client_search"].split()[1])).scalar()
            return render_template("no-template.html", all_clients=all_clients, client_chosen=client_chosen,
                                   selected_client=selected_client)
    return render_template("no-template.html", all_clients=all_clients, client_chosen=client_chosen)


@app.route("/create-template", methods=["GET", "POST"])
@login_required
def create_template():
    if request.method == "POST":
        new_template = EventInfo(event_summary=request.form["event_name"],
                                 description=request.form["event_description"],
                                 location=request.form["location"],
                                 color=EVENT_COLORS.get(request.form["event_color"]),
                                 recurring="yes",
                                 duration=request.form["meeting-duration"],
                                 appointment_use=10000,
                                 creator=current_user.user_id)
        with app.app_context():
            db.session.add(new_template)
            db.session.commit()
        return redirect(url_for("all_bookings"))
    return render_template("create_template.html")


@app.route("/all_templates", methods=["POST", "GET"])
@login_required
def all_templates():
    all_events = db.session.execute(db.select(EventInfo).filter_by(creator=current_user.user_id)).scalars()
    return render_template("all_templates.html", all_events=all_events)


if __name__ == "__main__":
    app.run(debug=True)
