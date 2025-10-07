from django.urls import path, include

# This list will grow as we add routes from each app
urlpatterns = [
    path('', include('friendships.urls')),
    path('', include('groups.urls')),
    path('', include('expenses.urls')),
    path('', include('payments.urls')),
]