from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser , JSONParser
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied
from .permissions import OnlyPayerCanDelete
from .permissions import IsExpenseActionAllowed
from rest_framework.decorators import action
from django.db import transaction
from .models import ExpenseActionRequest, ExpenseActionApproval
from .permissions import IsExpensePayer
from django.db.models import F
from rest_framework.permissions import IsAuthenticated

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
    parser_classes = [MultiPartParser, FormParser , JSONParser] # To support file uploads

    queryset = Expense.objects.all() \
        .select_related("group", "created_by", "updated_by") \
        .prefetch_related("participants", "payers", "attachments")

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        # >>> خیلی مهم: برای اکشن‌های detail هیچ فیلتری نزن
        if getattr(self, "action", None) in ("retrieve", "update", "partial_update", "destroy"):
            return qs

        # --- فقط برای لیست فیلتر کن ---
        # گروه‌هایی که عضو آنی (اسم related name را با مدل خودت تطبیق بده اگر فرق دارد)
        try:
            member_group_ids = user.group_memberships.values_list("group_id", flat=True)
        except Exception:
            member_group_ids = []

        # خرج‌های گروهی که عضویم
        group_q = Q(group_id__in=member_group_ids)

        # خرج‌های بی‌گروه که خودم payer/participant/creator هستم
        personal_q = Q(group__isnull=True) & (
                Q(payers__user_id=user.id) | Q(participants__user_id=user.id) | Q(created_by_id=user.id)
        )

        qs = qs.filter(group_q | personal_q).distinct()

        # فیلتر اختیاری group_id
        group_id = self.request.query_params.get("group_id")
        if group_id:
            qs = qs.filter(group_id=group_id)

        return qs

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

    def get_permissions(self):
        if self.action == "destroy":
            return [permissions.IsAuthenticated(), IsExpenseActionAllowed(), OnlyPayerCanDelete()]
        if self.action in ("update", "partial_update"):
            return [permissions.IsAuthenticated(), IsExpenseActionAllowed()]
        return [permissions.IsAuthenticated()]

    def perform_destroy(self, instance):
        instance.delete()

    def _payer_ids(self, expense):
        # paid_amount_minor > 0 => payer
        return set(expense.payers.filter(paid_amount_minor__gt=0).values_list("user_id", flat=True))

    def _serialize_request(self, req):
        return {
            "id": req.id,
            "action": req.action,
            "required_count": req.required_count,
            "is_completed": req.is_completed,
            "approvals": list(req.approvals.values_list("user__username", flat=True)),
            "created_at": req.created_at,
        }

    @action(detail=True, methods=["post"], url_path="request-delete", permission_classes = [IsAuthenticated, IsExpensePayer])
    def request_delete(self, request, pk=None):
        expense = self.get_object()
        payers = self._payer_ids(expense)
        if request.user.id not in payers:
            return Response({"detail": "Only payers can perform this action."}, status=status.HTTP_403_FORBIDDEN)
        if len(payers) <= 1:
            expense.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        with transaction.atomic():
            req = ExpenseActionRequest.objects.create(
                expense=expense,
                action=ExpenseActionRequest.ACTION_DELETE,
                payload=None,
                requested_by=request.user,
                required_count=len(payers),
            )
            ExpenseActionApproval.objects.get_or_create(request=req, user=request.user)
        return Response({"detail": "Delete request created", "request": self._serialize_request(req)},
                        status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="request-edit", permission_classes = [IsAuthenticated, IsExpensePayer])
    def request_edit(self, request, pk=None):
        expense = self.get_object()
        payers = self._payer_ids(expense)
        if request.user.id not in payers:
            return Response({"detail": "Only payers can perform this action."}, status=status.HTTP_403_FORBIDDEN)
        pending_patch = request.data or {}
        if len(payers) <= 1:
            serializer = self.get_serializer(expense, data=pending_patch, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data, status=status.HTTP_200_OK)

        with transaction.atomic():
            req = ExpenseActionRequest.objects.create(
                expense=expense,
                action=ExpenseActionRequest.ACTION_EDIT,
                payload=pending_patch,
                requested_by=request.user,
                required_count=len(payers),
            )
            ExpenseActionApproval.objects.get_or_create(request=req, user=request.user)
        return Response({"detail": "Edit request created", "request": self._serialize_request(req)},
                        status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="approve", permission_classes = [IsAuthenticated, IsExpensePayer])
    def approve(self, request, pk=None):
        expense = self.get_object()
        payers = self._payer_ids(expense)
        if request.user.id not in payers:
            return Response({"detail": "Only payers can perform this action."}, status=status.HTTP_403_FORBIDDEN)
        action_name = request.data.get("action")
        if action_name not in (ExpenseActionRequest.ACTION_DELETE, ExpenseActionRequest.ACTION_EDIT):
            return Response({"detail": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)

        req = (ExpenseActionRequest.objects
               .filter(expense=expense, action=action_name, is_completed=False)
               .order_by("-created_at")
               .select_for_update()
               .first())
        if not req:
            return Response({"detail": "No pending request"}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            ExpenseActionApproval.objects.get_or_create(request=req, user=request.user)
            if req.approvals.count() >= req.required_count:
                if req.action == ExpenseActionRequest.ACTION_DELETE:
                    type(req).objects.filter(pk=req.pk, is_completed=False).update(is_completed=True)
                    expense.delete()

                    return Response({"detail": "Expense deleted"}, status=status.HTTP_200_OK)
                else:
                    serializer = self.get_serializer(expense, data=req.payload or {}, partial=True)
                    serializer.is_valid(raise_exception=True)
                    self.perform_update(serializer)
                    req.is_completed = True
                    req.save(update_fields=["is_completed"])
                    return Response(serializer.data, status=status.HTTP_200_OK)

        return Response({"detail": "Approval recorded", "request": self._serialize_request(req)},
                        status=status.HTTP_202_ACCEPTED)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if len(self._payer_ids(instance)) > 1:
            return Response({"detail": "Use /request-delete/ then /approve/ by all payers."},
                            status=status.HTTP_409_CONFLICT)
        return super().destroy(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        if len(self._payer_ids(instance)) > 1:
            return Response({"detail": "Use /request-edit/ then /approve/ by all payers."},
                            status=status.HTTP_409_CONFLICT)
        return super().partial_update(request, *args, **kwargs)


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