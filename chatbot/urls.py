from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('chat/<str:session_id>/', views.chat_session, name='chat_session'),
    path('api/sessions/new/',views.new_session,name='new_session'),
    path('api/sessions/list/',views.session_list_api,name='session_list_api'),
    path('api/sessions/<str:session_id>/send/',views.send_message,name='send_message'),
    path('api/sessions/<str:session_id>/delete/',views.delete_session,name='delete_session'),
    path('api/sessions/<str:session_id>/rename/',views.rename_session,name='rename_session'),
    path('chat/<str:session_id>/messages/',views.session_messages_api,name='session_messages_api'),
    path('api/products/',views.product_search_api,name='product_search'),
    path('api/schema.json',views.api_schema_json,name='api_schema_json'),
    path('api/docs/',views.api_docs,name='api_docs'),
]