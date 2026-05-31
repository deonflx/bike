from django.urls import path
# pyrefly: ignore [missing-import]
from . import views

urlpatterns = [
    # Home / list
    path('', views.customer_list, name='customer_list'),

    # Form
    path('new-trip/', views.bike_form, name='bike_form'),
    path('submit/', views.bike_submit, name='bike_submit'),
    path('success/', views.bike_success, name='bike_success'),

    # Customer detail
    path('customers/<int:pk>/', views.customer_detail, name='customer_detail'),
    path('customers/<int:pk>/summary/', views.generate_customer_summary, name='customer_summary'),
    path('customers/<int:pk>/route/', views.view_route, name='view_route'),
    path('customers/<int:pk>/delete/', views.delete_trip, name='delete_trip'),

    # Live trip sessions
    path('customers/<int:pk>/start/', views.start_trip, name='start_trip'),
    path('session/<int:session_pk>/', views.trip_map, name='trip_map'),
    path('session/<int:session_pk>/update/', views.update_location, name='update_location'),
    path('session/<int:session_pk>/data/', views.session_data, name='session_data'),
    path('session/<int:session_pk>/end/', views.end_trip, name='end_trip'),
    
    # AI Advisor
    path('customers/<int:pk>/ai-tips/', views.generate_ai_tips, name='generate_ai_tips'),
]
