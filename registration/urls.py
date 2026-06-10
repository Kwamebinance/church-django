from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("register/pending/", views.reg_pending, name="reg_pending"),
    path("api/fellowships/", views.api_fellowships, name="api_fellowships"),
    path("api/cells/", views.api_cells, name="api_cells"),
    path("registrations/", views.approval_queue, name="reg_queue"),
    path("registrations/<uuid:req_id>/", views.review, name="reg_review"),
    path("reset/", views.reset_request, name="reset_request"),
    path("reset/verify/", views.reset_verify, name="reset_verify"),
]
