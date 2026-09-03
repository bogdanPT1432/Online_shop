import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quantum_portal.db'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'products')

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# --- МОДЕЛІ БАЗИ ДАНИХ ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)


class Position(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)
    characteristics = db.Column(db.Text, nullable=True)  # Характеристики товару
    category = db.Column(db.String(50), nullable=False, default='hardware')  # 'hardware' або 'games'
    file_name = db.Column(db.String(150), nullable=True)


class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('position.id'), nullable=False)
    product = db.relationship('Position')


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_price = db.Column(db.Float, nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- МАРШРУТИ ---

@app.route('/')
def index():
    products = Position.query.limit(4).all()
    return render_template('index.html', products=products)


@app.route('/catalog')
def catalog():
    cat = request.args.get('category')
    if cat:
        products = Position.query.filter_by(category=cat).all()
    else:
        products = Position.query.all()
    return render_template('catalog.html', products=products, active_category=cat)


@app.route('/position/<int:position_id>')
def position_detail(position_id):
    product = Position.query.get_or_404(position_id)
    return render_template('position_detail.html', product=product)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Невірний email або пароль', 'danger')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        user_exist = User.query.filter_by(email=email).first()
        if user_exist:
            flash('Користувач із таким email вже існує.', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password, method='scrypt')
        is_first_user = User.query.count() == 0

        new_user = User(username=username, email=email, password=hashed_password, is_admin=is_first_user)
        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        return redirect(url_for('index'))
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/add_position', methods=['GET', 'POST'])
@login_required
def add_position():
    if not current_user.is_admin:
        flash('Доступ заборонено.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name')
        price = float(request.form.get('price'))
        description = request.form.get('description')
        characteristics = request.form.get('characteristics')
        category = request.form.get('category')

        file = request.files.get('file')
        file_name = None
        if file and file.filename != '':
            file_name = secure_filename(file.filename)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], file_name))

        new_product = Position(
            name=name,
            price=price,
            description=description,
            characteristics=characteristics,
            category=category,
            file_name=file_name
        )
        db.session.add(new_product)
        db.session.commit()

        flash('Товар успішно додано!', 'success')
        return redirect(url_for('catalog'))
    return render_template('add_position.html')


@app.route('/delete_position/<int:position_id>', methods=['POST'])
@login_required
def delete_position(position_id):
    if not current_user.is_admin:
        flash('У вас немає прав для видалення товарів.', 'danger')
        return redirect(url_for('index'))

    product = Position.query.get_or_404(position_id)

    if product.file_name:
        image_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], product.file_name)
        if os.path.exists(image_path):
            os.remove(image_path)

    CartItem.query.filter_by(product_id=product.id).delete()
    db.session.delete(product)
    db.session.commit()

    flash('Товар успішно видалено!', 'success')
    return redirect(url_for('catalog'))


@app.route('/cart')
@login_required
def cart():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    total = sum(item.product.price for item in cart_items)
    return render_template('cart.html', cart_items=cart_items, total=total)


@app.route('/add_to_cart/<int:position_id>', methods=['POST'])
@login_required
def add_to_cart(position_id):
    product = Position.query.get_or_404(position_id)
    cart_item = CartItem(user_id=current_user.id, product_id=product.id)
    db.session.add(cart_item)
    db.session.commit()
    flash('Товар додано до кошика!', 'success')
    return redirect(url_for('cart'))


@app.route('/checkout', methods=['POST'])
@login_required
def checkout():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        flash('Кошик порожній!', 'warning')
        return redirect(url_for('cart'))

    total = sum(item.product.price for item in cart_items)
    new_order = Order(user_id=current_user.id, total_price=total)
    db.session.add(new_order)

    for item in cart_items:
        db.session.delete(item)

    db.session.commit()
    flash('Замовлення успішно оформлено!', 'success')
    return redirect(url_for('my_orders'))


@app.route('/my_orders')
@login_required
def my_orders():
    orders = Order.query.filter_by(user_id=current_user.id).all()
    return render_template('my_orders.html', orders=orders)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
    