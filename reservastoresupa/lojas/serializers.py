from .models import Loja, Produto, Categoria
from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class ProdutoSerializer(serializers.ModelSerializer):


    class Meta:
        model = Produto
        fields = '__all__'

    def get_imagem(self, obj):
        request = self.context.get("request")
        if obj.imagem:
            return request.build_absolute_uri(obj.imagem.url) if request else obj.imagem.url
        return None

    def validate_preco(self, value):
        if value < 0:
            raise serializers.ValidationError("O preço não pode ser negativo.")
        return value


class CategoriaSerializer(serializers.ModelSerializer):
    produtos = ProdutoSerializer(many=True, read_only=True)  # Inclui produtos dentro da categoria

    class Meta:
        model = Categoria
        fields = '__all__'

class LojaSerializer(serializers.ModelSerializer):
    categorias = CategoriaSerializer(many=True, read_only=True)  # Inclui categorias dentro da loja

    class Meta:
        model = Loja
        fields = '__all__'



class LojaPublicaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loja
        fields = ['id','nome', 'whatsapp', 'logo']  # Não inclui o 'dono'


from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        try:
            data = super().validate(attrs)  # Chama a validação padrão
        except Exception:
            raise serializers.ValidationError({"detail": "Usuário ou senha inválidos."})

        return data