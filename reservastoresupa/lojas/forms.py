import re
from django import forms
from .models import Loja


class LojaAdminForm(forms.ModelForm):
    email_contato = forms.EmailField(label="Email da loja ou do proprietário", required=True, help_text="Email público de contato. Informe o email comercial da loja ou o do dono.")

    class Meta:
        model = Loja
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nome"].label = "Nome da loja"
        self.fields["dono"].label = "Usuário do dono"
        self.fields["dono"].help_text = "Selecione a conta do proprietário. Use o botão + para cadastrar um usuário, se necessário."
        self.fields["whatsapp"].required = True

    def clean_whatsapp(self):
        value = self.cleaned_data["whatsapp"].strip()
        digits = re.sub(r"\D", "", value)
        if not re.fullmatch(r"\+?[\d()\s.-]+", value) or not 10 <= len(digits) <= 15:
            raise forms.ValidationError("Informe um telefone válido com DDD, usando de 10 a 15 dígitos.")
        return value
