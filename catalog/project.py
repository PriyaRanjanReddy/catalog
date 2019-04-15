from flask import Flask, render_template, request
from flask import redirect, jsonify, url_for, flash
from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Company, Icecream, User
from flask import session as login_session
import random
import string
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests

app = Flask(__name__)

CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Icecream Parlour"


# Connect to Database and create database session
engine = create_engine('sqlite:///icecream.db', connect_args={
    'check_same_thread': False}, echo=True)
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()


# Create anti-forgery state token
@app.route('/login')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    # return "The current session state is %s" % login_session['state']
    return render_template('login.html', STATE=state)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps(
            'Current user is already connected.'),
                                 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    # See if a user exists, if it doesn't make a new one

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 250px; height: 250px;border-radius: 150px; '
    flash("you are now logged in as %s" % login_session['username'])
    print "done!"
    return output


# User Helper Functions


def createUser(login_session):
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None


# DISCONNECT - Revoke a current user's token and reset their login_session
@app.route('/gdisconnect')
def gdisconnect():
        # Only disconnect a connected user.
    access_token = login_session.get('access_token')
    if access_token is None:
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]

    if result['status'] == '200':
        # Reset the user's sesson.
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']

        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        flash("you are logged out ")
        return redirect(url_for('showCompany'))
    else:
        # For whatever reason, the given token was invalid.
        response = make_response(
            json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


# JSON APIs to view specific Company Information
@app.route('/company/<int:company_id>/menu/JSON')
def companyJSON(company_id):
    company = session.query(Company).filter_by(id=company_id).one()
    items = session.query(Icecream).filter_by(company_id=company_id).all()
    return jsonify(Companies=[i.serialize for i in items])


# JSON APIs to view ice Cream information
@app.route('/company/<int:company_id>/menu/<int:menu_id>/JSON')
def icecreamJSON(company_id, menu_id):
    Menu_Item = session.query(Icecream).filter_by(id=menu_id).one()
    return jsonify(Menu_Item=Menu_Item.serialize)


# JSON APIs to view all Companies information
@app.route('/company/JSON')
def companiesJSON():
    companies = session.query(Company).all()
    return jsonify(companies=[r.serialize for r in companies])


# Show all Companies
@app.route('/')
@app.route('/company/')
def showCompany():
    companies = session.query(Company)
    return render_template('company.html', companies=companies)


# Create a new Company
@app.route('/company/new/', methods=['GET', 'POST'])
def newCompany():
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        if request.form['name']:
            newCompany = Company(
                name=request.form['name'], user_id=login_session['user_id'])
        session.add(newCompany)
        flash('New Company %s Successfully Created' % newCompany.name)
        session.commit()
        return redirect(url_for('showCompany'))
    else:
        return render_template('newCompany.html')


# Edit a Company
@app.route('/company/<int:company_id>/edit/', methods=['GET', 'POST'])
def editCompany(company_id):
    if 'username' not in login_session:
        flash('Please login first')
        return redirect('/login')
    editCompany = session.query(Company).filter_by(id=company_id).one()
    creator = getUserInfo(editCompany.user_id)
    user = getUserInfo(login_session['user_id'])
    if creator.id != login_session['user_id']:
        flash("Only creator can edit this company- "+creator.name)
        return redirect(url_for('showCompany'))
    if request.method == 'POST':
        if request.form['name']:
            editCompany.name = request.form['name']
            flash('Company Successfully Edited %s' % editCompany.name)
            return redirect(url_for('showCompany'))
    else:
        return render_template('editCompany.html', company=editCompany)


# Delete a Company
@app.route('/company/<int:company_id>/delete/', methods=['GET', 'POST'])
def deleteCompany(company_id):
    if 'username' not in login_session:
        return redirect('/login')
    companyToDelete = session.query(Company).filter_by(id=company_id).one()
    creator = getUserInfo(companyToDelete.user_id)
    user = getUserInfo(login_session['user_id'])
    if creator.id != login_session['user_id']:
        flash("Only creator can delete this company- "+creator.name)
        return redirect(url_for('showCompany'))
    if request.method == 'POST':
        session.delete(companyToDelete)
        flash('%s Successfully Deleted' % companyToDelete.name)
        session.commit()
        return redirect(url_for('showCompany', company_id=company_id))
    else:
        return render_template('deleteCompany.html', company=companyToDelete)


# Show a company menu
@app.route('/company/<int:company_id>/')
@app.route('/company/<int:company_id>/menu/')
def showMenu(company_id):
    company = session.query(Company).filter_by(id=company_id).one()
    items = session.query(Icecream).filter_by(company_id=company_id).all()
    creator = getUserInfo(company.user_id)
    return render_template(
        'menu.html', items=items, company=company, creator=creator)


# Create a new menu item
@app.route('/company/<int:company_id>/menu/new/', methods=['GET', 'POST'])
def newIcecream(company_id):
    if 'username' not in login_session:
        return redirect('/login')
    company = session.query(Company).filter_by(id=company_id).one()
    creator = getUserInfo(company.user_id)
    user = getUserInfo(login_session['user_id'])
    if creator.id != login_session['user_id']:
        flash("Only creator can make changes- "+creator.name)
        return redirect(url_for('showCompany'))
    if request.method == 'POST':
        newItem = Icecream(
            user_id=company.user_id,
            name=request.form['name'],
            description=request.form['description'],
            price=request.form['price'],
            company_id=company_id)
        session.add(newItem)
        session.commit()
        flash('New Icecream %s  Successfully Created' % (newItem.name))
        return redirect(url_for('showMenu', company_id=company_id))
    else:
        return render_template('newmenuitem.html', company_id=company_id)


# Edit a menu item
@app.route(
    '/company/<int:company_id>/menu/<int:menu_id>/edit',
    methods=['GET', 'POST'])
def editIcecream(company_id, menu_id):
    if 'username' not in login_session:
        return redirect('/login')
    editIcecream = session.query(Icecream).filter_by(id=menu_id).one()
    company = session.query(Company).filter_by(id=company_id).one()
    creator = getUserInfo(editIcecream.user_id)
    user = getUserInfo(login_session['user_id'])
    if creator.id != login_session['user_id']:
        flash("Only creator can edit this icecream-"+creator.name)
        return redirect(url_for('showCompany'))
    if request.method == 'POST':
        if request.form['name']:
            editIcecream.name = request.form['name']
        if request.form['description']:
            editIcecream.description = request.form['description']
        if request.form['price']:
            editIcecream.price = request.form['price']
        session.add(editIcecream)
        session.commit()
        flash('Icecream Successfully Edited')
        return redirect(url_for('showMenu', company_id=company_id))
    else:
        return render_template(
            'editmenuitem.html',
            company_id=company_id,
            menu_id=menu_id,
            item=editIcecream)


# Delete a menu item
@app.route(
    '/company/<int:company_id>/menu/<int:menu_id>/delete',
    methods=['GET', 'POST'])
def deleteIcecream(company_id, menu_id):
    if 'username' not in login_session:
        return redirect('/login')
    companyToDelete = session.query(Company).filter_by(id=company_id).one()
    icecreamToDelete = session.query(Icecream).filter_by(id=menu_id).one()
    creator = getUserInfo(companyToDelete.user_id)
    user = getUserInfo(login_session['user_id'])
    if creator.id != login_session['user_id']:
        flash("Only creator can delete-"+creator.name)
        return redirect(url_for('showCompany'))
    if request.method == 'POST':
        session.delete(icecreamToDelete)
        session.commit()
        flash('Icecream is Successfully Deleted')
        return redirect(url_for('showMenu', company_id=company_id))
    else:
        return render_template('deletemenuitem.html', item=icecreamToDelete)


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
