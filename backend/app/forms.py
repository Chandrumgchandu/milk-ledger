from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, PasswordField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, EqualTo, Length, Optional


class LoginForm(FlaskForm):
    phone = StringField("Owner Phone", validators=[DataRequired(), Length(max=20)])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")


class ForgotPasswordForm(FlaskForm):
    phone = StringField("Owner Phone", validators=[DataRequired(), Length(max=20)])
    recovery_key = PasswordField("Recovery Key", validators=[DataRequired(), Length(max=255)])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("new_password")])
    submit = SubmitField("Reset Password")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current Password", validators=[DataRequired(), Length(max=128)])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("new_password")])
    submit = SubmitField("Update Password")


class FarmerForm(FlaskForm):
    unique_code = StringField("Farmer ID", validators=[DataRequired(), Length(max=10)])
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    phone = StringField("Phone", validators=[DataRequired(), Length(max=20)])
    village = StringField("Village", validators=[Optional(), Length(max=120)])
    is_active = BooleanField("Active")
    submit = SubmitField("Save Farmer")


class EntryForm(FlaskForm):
    farmer_id = SelectField("Farmer", coerce=int, validators=[DataRequired()])
    date = DateField("Date", validators=[DataRequired()])
    session = SelectField("Session", choices=[("morning", "Morning"), ("evening", "Evening")], validators=[DataRequired()])
    quantity = StringField("Quantity (Liters)", validators=[DataRequired()])
    rate = StringField("Rate", validators=[DataRequired()])
    submit = SubmitField("Save Entry")


class PaymentForm(FlaskForm):
    farmer_id = SelectField("Farmer", coerce=int, validators=[DataRequired()])
    payment_date = DateField("Payment Date", validators=[DataRequired()])
    amount_paid = StringField("Amount Paid", validators=[DataRequired()])
    note = StringField("Note", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Save Payment")


class RateForm(FlaskForm):
    rate = StringField("New Rate", validators=[DataRequired()])
    submit = SubmitField("Update Rate")


class StoreTransactionForm(FlaskForm):
    farmer_id = SelectField("Farmer", coerce=int, validators=[DataRequired()])
    bill_date = DateField("Bill Date", validators=[DataRequired()])
    note = StringField("Note", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Save Store Bill")


class StoreFilterForm(FlaskForm):
    search = StringField("Search Farmer", validators=[Optional(), Length(max=120)])
    month = SelectField("Month", coerce=int, validators=[DataRequired()])
    year = StringField("Year", validators=[DataRequired(), Length(max=4)])
    submit = SubmitField("Apply")


class SettlementActionForm(FlaskForm):
    farmer_id = SelectField("Farmer", coerce=int, validators=[DataRequired()])
    settlement_month = DateField("Settlement Month", validators=[DataRequired()])
    note = TextAreaField("Note", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Lock Settlement")


class PaymentLogForm(FlaskForm):
    farmer_id = SelectField("Farmer", coerce=int, validators=[DataRequired()])
    payment_date = DateField("Payment Date", validators=[DataRequired()])
    amount = StringField("Amount", validators=[DataRequired()])
    direction = SelectField(
        "Direction",
        choices=[("to_farmer", "Pay Farmer"), ("from_farmer", "Recover From Farmer")],
        validators=[DataRequired()],
    )
    note = StringField("Note", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Save Settlement Payment")
