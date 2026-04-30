from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from models import Transaction

account_bp = Blueprint('account', __name__, url_prefix='/account')

@account_bp.route('/dashboard')
@login_required
def dashboard():
    recent = Transaction.query.filter_by(user_id=current_user.id)\
        .order_by(Transaction.created_at.desc()).limit(5).all()
    return render_template('account/dashboard.html', transactions=recent)

@account_bp.route('/topup', methods=['GET', 'POST'])
@login_required
def topup():
    if request.method == 'POST':
        try:
            amount = float(request.form.get('amount', 0))
        except ValueError:
            flash('Invalid amount.', 'danger')
            return render_template('account/topup.html')

        if amount < 10 or amount > 1000:
            flash('Amount must be between 10 and 1000 TWD.', 'danger')
            return render_template('account/topup.html')

        current_user.balance += amount
        txn = Transaction(
            user_id=current_user.id,
            amount=amount,
            type='topup',
            description=f'Top-up of {amount:.2f} TWD'
        )
        db.session.add(txn)
        db.session.commit()
        flash(f'Successfully added {amount:.2f} TWD to your balance.', 'success')
        return redirect(url_for('account.dashboard'))

    return render_template('account/topup.html')

@account_bp.route('/transactions')
@login_required
def transactions():
    page = request.args.get('page', 1, type=int)
    pagination = Transaction.query.filter_by(user_id=current_user.id)\
        .order_by(Transaction.created_at.desc())\
        .paginate(page=page, per_page=10, error_out=False)
    return render_template('account/transactions.html', pagination=pagination)

@account_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_new_password = request.form.get('confirm_new_password', '')

        if email and email != current_user.email:
            from models import User
            if User.query.filter_by(email=email).first():
                flash('Email already in use.', 'danger')
                return render_template('account/profile.html')
            current_user.email = email
            db.session.commit()
            flash('Email updated successfully.', 'success')

        if current_password:
            if not check_password_hash(current_user.password_hash, current_password):
                flash('Current password is incorrect.', 'danger')
                return render_template('account/profile.html')
            if new_password != confirm_new_password:
                flash('New passwords do not match.', 'danger')
                return render_template('account/profile.html')
            if not new_password:
                flash('New password cannot be empty.', 'danger')
                return render_template('account/profile.html')
            current_user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash('Password updated successfully.', 'success')

    return render_template('account/profile.html')
