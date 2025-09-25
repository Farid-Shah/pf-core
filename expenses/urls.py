from rest_framework.routers import DefaultRouter
from .views import (
    ExpenseViewSet,
    CategoryViewSet,
    ExpenseCommentViewSet,
    RecurringExpenseTemplateViewSet,
)

router = DefaultRouter()
router.register(r'expenses', ExpenseViewSet, basename='expense')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'comments', ExpenseCommentViewSet, basename='expense-comment')
router.register(r'recurring-expenses', RecurringExpenseTemplateViewSet, basename='recurring-expense')

urlpatterns = router.urls