from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.serializers import UserSerializer
from .models import Payment

User = get_user_model()

class PaymentSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and viewing payments.
    
    Handles the conversion between a user-friendly decimal 'amount' and
    the internal integer 'amount_minor'.
    """
    from_user = UserSerializer(read_only=True)
    to_user = UserSerializer(read_only=True)
    
    # Write-only field for specifying the recipient by their ID
    to_user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='to_user', write_only=True
    )
    
    # A user-friendly field for amount input/output
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=settings.SITE_CURRENCY_MINOR_UNITS, write_only=True
    )

    class Meta:
        model = Payment
        fields = [
            'id',
            'from_user',
            'to_user',
            'to_user_id', # For write operations
            'amount_minor', # Read-only, internal representation
            'amount',       # Write-only, user-friendly representation
            'group',
            'method',
            'status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'from_user',
            'to_user',
            'amount_minor',
            'status', # Status should likely be controlled by a service, not direct input
            'created_at',
            'updated_at',
        ]

    def to_representation(self, instance):
        """
        Convert `amount_minor` back to a decimal string for API responses.
        """
        representation = super().to_representation(instance)
        
        # Create a user-friendly 'amount' field in the output
        minor_units = 10 ** settings.SITE_CURRENCY_MINOR_UNITS
        representation['amount'] = (
            Decimal(instance.amount_minor) / minor_units
        ).quantize(Decimal('0.01'))
        
        return representation

    def validate(self, data):
        """
        Validate that a user cannot make a payment to themselves and set the sender.
        """
        request_user = self.context['request'].user
        if request_user == data['to_user']:
            raise serializers.ValidationError("You cannot make a payment to yourself.")
        
        # Set the sender of the payment
        data['from_user'] = request_user
        
        # Convert the decimal 'amount' to 'amount_minor'
        amount_decimal = data.pop('amount')
        minor_units = 10 ** settings.SITE_CURRENCY_MINOR_UNITS
        data['amount_minor'] = int(amount_decimal * minor_units)
        
        return data