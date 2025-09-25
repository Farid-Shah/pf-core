from django.db.models import Q
from rest_framework import viewsets, permissions, mixins

from .models import Payment
from .serializers import PaymentSerializer

class PaymentViewSet(mixins.CreateModelMixin,
                   mixins.RetrieveModelMixin,
                   mixins.ListModelMixin,
                   viewsets.GenericViewSet):
    """
    ViewSet for creating and viewing payments.
    
    Update and delete are disabled for now, as payment records are typically immutable.
    
    Endpoints:
    - GET /api/v1/payments/ - List payments sent or received by the user.
    - POST /api/v1/payments/ - Create a new payment.
    - GET /api/v1/payments/{id}/ - Retrieve a specific payment.
    """
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Users should only see payments where they are the sender or the recipient.
        """
        user = self.request.user
        return Payment.objects.filter(Q(from_user=user) | Q(to_user=user))

    def perform_create(self, serializer):
        """
        The serializer handles setting the `from_user` and converting the amount.
        We just need to call save.
        """
        serializer.save()