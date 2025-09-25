from rest_framework import serializers
from django.db import transaction

from accounts.serializers import UserSerializer
from .models import (
    Category,
    Expense,
    ExpensePayer,
    ExpenseParticipant,
    ExpenseComment,
    Attachment,
    RecurringExpenseTemplate,
)

# --- Category Serializer ---
class CategorySerializer(serializers.ModelSerializer):
    """
    Serializer for the Category model, supporting parent-child relationships.
    """
    class Meta:
        model = Category
        fields = ['id', 'name', 'parent']

# --- Comment and Attachment Serializers ---
class ExpenseCommentSerializer(serializers.ModelSerializer):
    """
    Serializer for expense comments. The user is automatically set to the request user.
    """
    user = UserSerializer(read_only=True)

    class Meta:
        model = ExpenseComment
        fields = ['id', 'user', 'content', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

class AttachmentSerializer(serializers.ModelSerializer):
    """
    Serializer for expense attachments.
    """
    class Meta:
        model = Attachment
        fields = ['id', 'file', 'content_type', 'size_bytes', 'created_at']
        read_only_fields = ['id', 'content_type', 'size_bytes', 'created_at']


# --- Expense Split and Payer/Participant Serializers ---
class ExpensePayerSerializer(serializers.ModelSerializer):
    """Read-only serializer for displaying who paid for an expense."""
    user = UserSerializer(read_only=True)

    class Meta:
        model = ExpensePayer
        fields = ['user', 'paid_amount_minor']

class ExpenseParticipantSerializer(serializers.ModelSerializer):
    """Read-only serializer for displaying who owes for an expense."""
    user = UserSerializer(read_only=True)

    class Meta:
        model = ExpenseParticipant
        fields = ['user', 'owed_amount_minor']


class ExpenseSplitSerializer(serializers.Serializer):
    """
    Write-only serializer to validate the structure for splitting an expense.
    This is used inside the main Expense serializer.
    """
    user_id = serializers.UUIDField()
    paid_amount_minor = serializers.IntegerField(min_value=0, default=0)
    owed_amount_minor = serializers.IntegerField(min_value=0, default=0)


# --- Main Expense Serializers ---
class ExpenseSerializer(serializers.ModelSerializer):
    """
    Basic serializer for listing expenses.
    """
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = Expense
        fields = [
            'id',
            'description',
            'total_amount_minor',
            'date',
            'group',
            'created_by',
        ]


class ExpenseDetailSerializer(ExpenseSerializer):
    """
    Detailed serializer for creating, retrieving, and updating an expense.
    It handles the nested creation of payers and participants via a 'splits' field.
    """
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True, required=False, allow_null=True
    )
    payers = ExpensePayerSerializer(many=True, read_only=True)
    participants = ExpenseParticipantSerializer(many=True, read_only=True)
    comments = ExpenseCommentSerializer(many=True, read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)

    # Write-only field for creating/updating splits in a "Splitwise-style"
    splits = serializers.ListField(
        child=ExpenseSplitSerializer(), write_only=True
    )

    class Meta(ExpenseSerializer.Meta):
        fields = ExpenseSerializer.Meta.fields + [
            'details',
            'category',
            'category_id',
            'updated_by',
            'payers',
            'participants',
            'comments',
            'attachments',
            'splits', # For write operations
        ]
        read_only_fields = ['created_by', 'updated_by']

    def validate(self, data):
        """
        Validate that the sum of splits matches the total amount of the expense.
        """
        total_amount = data.get('total_amount_minor')
        splits = data.get('splits')

        paid_sum = sum(split.get('paid_amount_minor', 0) for split in splits)
        owed_sum = sum(split.get('owed_amount_minor', 0) for split in splits)

        # Using a tolerance for floating point inaccuracies is good practice, but with minor units (integers) it's simpler.
        if paid_sum != total_amount:
            raise serializers.ValidationError(
                f"The sum of paid amounts ({paid_sum}) must equal the expense total ({total_amount})."
            )

        if owed_sum != total_amount:
            raise serializers.ValidationError(
                f"The sum of owed amounts ({owed_sum}) must equal the expense total ({total_amount})."
            )
        return data

    def create(self, validated_data):
        """
        Create the expense and its associated payers and participants in a single transaction.
        """
        splits_data = validated_data.pop('splits')
        validated_data['created_by'] = self.context['request'].user

        with transaction.atomic():
            expense = Expense.objects.create(**validated_data)
            for split_data in splits_data:
                user_id = split_data['user_id']
                if split_data['paid_amount_minor'] > 0:
                    ExpensePayer.objects.create(
                        expense=expense,
                        user_id=user_id,
                        paid_amount_minor=split_data['paid_amount_minor']
                    )
                if split_data['owed_amount_minor'] > 0:
                    ExpenseParticipant.objects.create(
                        expense=expense,
                        user_id=user_id,
                        owed_amount_minor=split_data['owed_amount_minor']
                    )
        return expense

    def update(self, instance, validated_data):
        """
        Update an expense and its splits. This replaces the old splits with the new ones.
        """
        splits_data = validated_data.pop('splits', None)
        validated_data['updated_by'] = self.context['request'].user

        with transaction.atomic():
            # Update the Expense instance
            instance = super().update(instance, validated_data)

            # If new splits data is provided, clear old splits and create new ones
            if splits_data is not None:
                instance.payers.all().delete()
                instance.participants.all().delete()
                for split_data in splits_data:
                    user_id = split_data['user_id']
                    if split_data['paid_amount_minor'] > 0:
                        ExpensePayer.objects.create(
                            expense=instance,
                            user_id=user_id,
                            paid_amount_minor=split_data['paid_amount_minor']
                        )
                    if split_data['owed_amount_minor'] > 0:
                        ExpenseParticipant.objects.create(
                            expense=instance,
                            user_id=user_id,
                            owed_amount_minor=split_data['owed_amount_minor']
                        )
        return instance

# --- Recurring Expense Serializer ---
class RecurringExpenseTemplateSerializer(serializers.ModelSerializer):
    """
    Serializer for recurring expense templates.
    """
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = RecurringExpenseTemplate
        fields = [
            'id',
            'group',
            'description',
            'amount_minor',
            'schedule',
            'next_run_at',
            'is_active',
            'created_by',
        ]
        read_only_fields = ['created_by']