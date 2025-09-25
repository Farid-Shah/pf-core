from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from .models import (
    Expense,
    Category,
    ExpenseComment,
    RecurringExpenseTemplate,
    Attachment,
)
from .serializers import (
    ExpenseSerializer,
    ExpenseDetailSerializer,
    CategorySerializer,
    ExpenseCommentSerializer,
    RecurringExpenseTemplateSerializer,
    AttachmentSerializer,
)

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for listing expense categories.
    
    Endpoint:
    - GET /api/v1/categories/
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]


class ExpenseViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Expenses.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser] # To support file uploads

    def get_queryset(self):
        """
        Filter expenses to only those in groups the user is a member of.
        Also supports filtering by a `group_id` query parameter.
        """
        user = self.request.user
        # Get IDs of all groups the user is a member of
        member_of_groups = user.group_memberships.values_list('group_id', flat=True)
        queryset = Expense.objects.filter(group_id__in=member_of_groups)

        # Further filter by group_id if provided in the query params
        group_id = self.request.query_params.get('group_id')
        if group_id:
            queryset = queryset.filter(group_id=group_id)
            
        return queryset

    def get_serializer_class(self):
        """
        Use a lightweight serializer for list views and a detailed one for other actions.
        """
        if self.action == 'list':
            return ExpenseSerializer
        return ExpenseDetailSerializer

    def perform_create(self, serializer):
        """
        Handle expense and potential file attachment creation.
        The serializer itself handles the creation of splits.
        """
        expense = serializer.save(created_by=self.request.user)
        
        # Handle file attachments uploaded alongside the expense
        files = self.request.FILES.getlist('attachments')
        for file in files:
            Attachment.objects.create(
                expense=expense,
                file=file,
                content_type=file.content_type,
                size_bytes=file.size
            )


class ExpenseCommentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing comments on expenses.
    Supports filtering by `expense_id`.
    """
    serializer_class = ExpenseCommentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filter comments based on the `expense_id` query parameter.
        """
        queryset = ExpenseComment.objects.select_related('user', 'expense').all()
        expense_id = self.request.query_params.get('expense_id')
        if expense_id:
            queryset = queryset.filter(expense_id=expense_id)
        # TODO: Add a permission check to ensure user can see these comments.
        return queryset

    def perform_create(self, serializer):
        """
        Set the user of the comment to the request user.
        """
        serializer.save(user=self.request.user)


class RecurringExpenseTemplateViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing recurring expense templates.
    """
    serializer_class = RecurringExpenseTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Users should only see recurring expenses from groups they are in.
        """
        user = self.request.user
        member_of_groups = user.group_memberships.values_list('group_id', flat=True)
        return RecurringExpenseTemplate.objects.filter(group_id__in=member_of_groups)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)