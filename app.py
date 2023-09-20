from flask import Flask, request, render_template, redirect, url_for , g , jsonify , make_response , session, flash
from flask_httpauth import HTTPBasicAuth
import firebase_admin
from firebase_admin import credentials, db
import random

app = Flask(__name__)
auth = HTTPBasicAuth()

# Initialize Firebase
cred = credentials.Certificate('ranking-intern-firebase-adminsdk-ojxmo-32e9590c3d.json')
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://ranking-intern-default-rtdb.firebaseio.com'
})

# Initialize a set to keep track of generated IDs
generated_ids = set()
admin_username = "admin"
admin_password = "12345"
app.secret_key = "axbcyd"

#func to generate user_ids
def generate_user_id():
    while True:
        # Generate a random 4-digit user ID
        user_id = random.randint(1000, 9999)
        user_id_str = str(user_id).zfill(4)

        # Check if the generated ID is unique, if not, regenerate
        if user_id_str not in generated_ids:
            generated_ids.add(user_id_str)
            return user_id_str
    

logged_in_users = {}

@auth.verify_password
def verify_password(username, password):
    if username == admin_username and password == admin_password:
        session['user'] = username
        logged_in_users[username] = True
        return True
    return False

@auth.error_handler
def unauthorized():
    response = make_response(jsonify({'error': 'Unauthorized access'}), 401)
    response.headers['WWW-Authenticate'] = 'Basic realm="Login Required"'
    return response

#---------------------------------------------------------------------------------#
#Main Routes for App

@app.route('/', methods=['GET', 'POST'])
@auth.login_required
def home():
    error_message = None

    if request.method == 'POST':
        entered_password = request.form.get('password')
        if entered_password == admin_password:
            # Password is correct, redirect to the home page
            return render_template('home.html')
        else:
            # Password is incorrect, set an error message
            error_message = "Wrong password. Please try again."

    # Render the admin login page with or without an error message
    return render_template('admin_login.html', error_message=error_message)



@app.route('/admin_login', methods=['GET'])
def admin_login():
    return render_template('admin_login.html')



@app.route('/register_user', methods=['GET', 'POST'])
def register_user():
    if request.method == 'POST':
        # Get user registration data from the form
        name = request.form['name']
        age = int(request.form['age'])
        gender = request.form['gender']
        gender_preference = request.form.getlist('gender_preference')
        interests = request.form.getlist('interests')
        min_age_preference = int(request.form['min_age'])
        max_age_preference = int(request.form['max_age'])
        vipdata = bool(request.form.get('vip', False))
        locactivity = bool(request.form.get('activity', False))

        user_id = generate_user_id()

        # Create a user profile dictionary
        user_profile = {
            "user_id": str(user_id),
            "name": name,
            "age": int(age),
            "gender": gender,
            "gender_preference": gender_preference,
            "interests": interests,
            "min_age_preference": min_age_preference,
            "max_age_preference": max_age_preference,
            "vip": vipdata,
            "activity": locactivity,
            # Add more fields as needed
        }

        # Store the user's profile in the "users" collection in Firebase
        db.reference('users').child(user_id).set(user_profile)

        # Redirect to a confirmation or home page
        return redirect(url_for('home'))

    return render_template('user_details.html')



@app.route('/database')
@auth.login_required
def database():
    # Fetch data for both guys and girls from the Firebase Realtime Database
    girls_data = db.reference('girls').get()
    guys_data = db.reference('guys').get()
    

    return render_template('database.html', girls=girls_data, guys=guys_data)



@app.route('/swipe_data')
@auth.login_required
def swipe_data():
    users_ref = db.reference('users')
    swipes_ref = db.reference('swipes')

    users_data = users_ref.get()
    user_swipes_mapping = {}

    for user_id, user_data in users_data.items():
        user_name = user_data.get('name')
        swipes = swipes_ref.child(user_name).get()
        user_swipes_mapping[user_name] = swipes

    left_swipes = {}
    right_swipes = {}

    for user, swipes in user_swipes_mapping.items():
        left_swipes[user] = []
        right_swipes[user] = []

        if swipes:
            for target_user, direction in swipes.items():
                if direction == 'left':
                    left_swipes[user].append(target_user)
                elif direction == 'right':
                    right_swipes[user].append(target_user)


    for user, swipes in left_swipes.items():
        db.reference(f'swipe_usernames/names/{user}/left_swipes').set(swipes)

    for user, swipes in right_swipes.items():
        db.reference(f'swipe_usernames/names/{user}/right_swipes').set(swipes)

    return render_template('swipe_database.html', left_swipes=left_swipes, right_swipes=right_swipes,)




# Route for the swipe page
@app.route('/swipe', methods=['GET', 'POST'])
def swipe():
    selected_user_id = None
    remaining_users = []  # Initialize a list for remaining users
    users_ref = db.reference('users')

    if request.method == 'POST':
        selected_user_id = request.form.get('selected_user')
        selected_user_data = users_ref.child(selected_user_id).get()
        selected_user_name = selected_user_data.get('name')
        swipes = {}

        for user_id, user_data in users_ref.get().items():
            if user_id != selected_user_id:  # Exclude the selected user
                swipe_direction = request.form.get(f'swipe_{user_id}')
                if swipe_direction:
                    swipes[user_data.get('name')] = swipe_direction

        db.reference('swipes').child(selected_user_name).set(swipes)

    users_data = users_ref.get()
    if selected_user_id:
        remaining_users = [user_id for user_id in users_data if user_id != selected_user_id]

    return render_template('swipe_select.html', users_data=users_data, selected_user=selected_user_id, remaining_users=remaining_users)



@app.route('/rank_users', methods=['GET', 'POST'])
def rank_users():
    selected_user_name = None
    selected_user_age = None
    selected_user_gender = None
    selected_user_gender_pref = None
    selected_user_swipe = None
    max_age_data = None
    min_age_data = None
    ranked_users = []

    if request.method == 'POST':
        # Retrieve the selected user's details from the database
        selected_user_name = request.form.get('selected_user_name')
        selected_user_data = None
        swipes_match = None

        # Retrieve the user_id for the selected user using their name
        users_ref = db.reference('users')
        users_data = users_ref.get()

        for user_id, user_data in users_data.items():
            if user_data.get('name') == selected_user_name:
                selected_user_data = user_data
                break

        swipes_ref = db.reference('swipe_usernames')
        swipes_data = swipes_ref.get()  
        
        if 'names' in swipes_data:
            names_data = swipes_data['names']
            if selected_user_name in names_data:
                swipes_match = names_data[selected_user_name]


        print("SIKE1:",selected_user_name)
        print("SIKE:",swipes_match)

        # print("DATA:",selected_user_data)
        selected_user_age = selected_user_data.get('age')
        max_age_data = selected_user_data.get('max_age_preference')
        min_age_data = selected_user_data.get('min_age_preference')    
        selected_user_gender = selected_user_data.get('gender')  
        selected_user_gender_pref = selected_user_data.get('gender_preference')
        if swipes_match is not None:
            selected_user_swipe = swipes_match.get('right_swipes', [])
        else:
            selected_user_swipe = []  
        # Now, selected_user_data contains the data of the selected user

        # print("DATA:",selected_user_swipe)
        # print("DATAGENDER:",selected_user_gender_pref)debbugging line
        scores = db.reference('scores').get()
        common_interests_weight = scores['interests_match'].get('value', 0)
        swipe_right_weight = scores['swipe_right'].get('value', 0)
        activity_weight = scores['activity'].get('value', 0)
        vip_weight = scores['VIP'].get('value', 0)
        age_weight_inside_range = scores['age_closeness'].get('value', 0)
        age_weight_outside_range = age_weight_inside_range - 1
        
        
        # Retrieve details of all users from the database
        all_users = db.reference('users').get()

        for user_id, user_data in all_users.items():
            if user_id != selected_user_name:
                user_gender = user_data.get('gender')
                # print("DATAGENDER2:",user_gender)debbugging line
                if user_gender in selected_user_gender_pref:
                    if user_data.get('activity', False):
                    # Calculate the score based on the provided formula
                        no_interests = len(user_data.get('interests', []))
                        common_interests = len(set(user_data.get('interests', [])) & set(selected_user_data.get('interests', [])))
                        # swipe_right = user_data.get('swipes', {}).get(selected_user_name) == 'right'
                        swipe_right = ( swipes_match is not None and 'right_swipes' in swipes_match and user_data.get('name') in swipes_match['right_swipes'] )
                        activity = user_data.get('activity', False)
                        vip = user_data.get('vip', False)
                        # print("SWIPECALCDATA:",swipe_right) debbugging line
                        # Retrieve the user's name from their data (assuming it's stored under 'name')
                        user_name = user_data.get('name', '')

                        # Calculate age closeness weight based on whether the user's age is inside or outside the selected user's range
                        user_age = user_data.get('age', 0)
                        selected_user_min_age = selected_user_data.get('min_age_preference', 18)
                        selected_user_max_age = selected_user_data.get('max_age_preference', 60)

                        if selected_user_min_age <= user_age <= selected_user_max_age:
                            age_closeness_weight = age_weight_inside_range
                        else:
                            # Calculate a lower age closeness weight for users outside the range
                            age_diff = min(abs(user_age - selected_user_min_age), abs(user_age - selected_user_max_age))
                            age_closeness_weight = age_weight_outside_range / (age_diff + 1)

                        print("TESTER:",common_interests)
                        score = (common_interests_weight / (no_interests + 1)) * common_interests + \
                                (swipe_right_weight * swipe_right) + \
                                (activity_weight * activity) + \
                                (vip_weight * vip) + \
                                (age_closeness_weight * age_weight_inside_range)
                        
                        score = round(score, 2)

                        # Store user_name and score in a dictionary
                        aged = user_data.get('age', 0)
                        genderd = user_data.get('gender', 0)
                        pref = user_data.get('gender_preference',0)
                        interests = user_data.get('interests',0)
                        vipuser = user_data.get('vip',0)
                        locactivity = user_data.get('activity',0)
                        minage = user_data.get('min_age_preference',0)
                        maxage = user_data.get('max_age_preference',0)
                        ranked_users.append({'user_name': user_name, 'score': score , 'age': aged , 'genderd':genderd , 'pref':pref , 'interests':interests , 'vipuser':vipuser , 'locactivity':locactivity , 'minage':minage , 'maxage':maxage})


        # Sort the users based on their scores in descending order
        ranked_users.sort(key=lambda x: x['score'], reverse=True)

        # Remove the selected user from the ranking table
        ranked_users = [user for user in ranked_users if user['user_name'] != selected_user_name]
        

    # Retrieve the user names by iterating over the 'users' node's children
    user_names = [user_data.get('name') for user_data in db.reference('users').get().values()]

    return render_template('ranked_users.html', user_names=user_names, selected_user_swipe=selected_user_swipe,selected_user_gender_pref=selected_user_gender_pref,selected_user_gender=selected_user_gender,selected_user_age=selected_user_age, selected_user_name=selected_user_name, ranked_users=ranked_users , max_age_data = max_age_data , min_age_data = min_age_data)


if __name__ == "__main__":
    app.run(debug=True)

