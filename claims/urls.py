"""
URL routing for claims app
"""

from django.urls import path
from . import views

app_name = 'claims'

urlpatterns = [
    # Document upload and management
    path('', views.document_list, name='document_list'),
    path('upload/', views.document_upload, name='document_upload'),
    path('document/<int:pk>/', views.document_detail, name='document_detail'),
    path('document/<int:pk>/status/', views.document_status, name='document_status'),
    path('document/<int:pk>/delete/', views.document_delete, name='document_delete'),
    path('document/<int:pk>/tags/', views.document_update_tags, name='document_update_tags'),

    # Protected media access (authentication required)
    path('document/<int:pk>/download/', views.document_download, name='document_download'),
    path('document/<int:pk>/view/', views.document_view_inline, name='document_view'),

    # Signed URL access (time-limited, no session required after validation)
    path('document/s/<str:token>/download/', views.document_download_signed, name='document_download_signed'),
    path('document/s/<str:token>/view/', views.document_view_signed, name='document_view_signed'),

    # Denial Decoder
    path('decode/', views.denial_decoder_upload, name='denial_decoder'),
    path('decode/<int:pk>/', views.denial_decoder_result, name='denial_decoder_result'),
    path('decode/<int:pk>/status/', views.denial_decoder_status, name='denial_decoder_status'),

    # Rating Analyzer
    path('rating-analyzer/', views.rating_analyzer_upload, name='rating_analyzer'),
    path('rating-analyzer/<int:pk>/', views.rating_analyzer_result, name='rating_analyzer_result'),
    path('rating-analyzer/<int:pk>/status/', views.rating_analyzer_status, name='rating_analyzer_status'),

    # Document Sharing with VSO
    path('document/<int:pk>/share/', views.document_share, name='document_share'),
    path('document/<int:pk>/share/<int:share_pk>/revoke/', views.document_unshare,
         name='document_unshare'),
]
