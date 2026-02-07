from django import forms


class DeliveryNoteForm(forms.Form):
    delivery_note = forms.CharField(required=False, widget=forms.Textarea)


class DisputeForm(forms.Form):
    reason = forms.CharField(max_length=120)
    details = forms.CharField(required=False, widget=forms.Textarea)


class OrderCheckoutForm(forms.Form):
    quantity = forms.IntegerField(min_value=1)
