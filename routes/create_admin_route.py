# from models import (
#     db,
#     User
# )

# def register_create_admin_route(app):

#     @app.route("/create-admin")
#     def create_admin():

#         existing_user = User.query.filter_by(
#             username="admin"
#         ).first()

#         if existing_user:

#             return "Admin already exists"

#         user = User(
#             username="admin",
#             role="ADMIN"
#         )

#         user.set_password(
#             "admin123"
#         )

#         db.session.add(user)

#         db.session.commit()

#         return "Admin Created"