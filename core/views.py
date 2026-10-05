from decimal import Decimal, InvalidOperation
from datetime import timedelta
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from .authorization import doctor_patient_queryset
from .forms import (
    AdmissionForm,
    AppointmentForm,
    ConsultationForm,
    DischargeForm,
    InpatientDepositForm,
    PatientDocumentForm,
    PatientForm,
    PrescriptionItemFormSet,
    appointment_slot_conflicts,
)
from .models import (
    Admission,
    Appointment,
    AuditEvent,
    Bed,
    Consultation,
    Adjustment,
    Dispensing,
    DispensingLine,
    HospitalSettings,
    Invoice,
    InvoiceLine,
    Medicine,
    MedicineBatch,
    Patient,
    Payment,
    PaymentMethod,
    PharmacySale,
    PharmacySaleLine,
    PharmacyReturn,
    Refund,
    Prescription,
    PrescriptionItem,
    ReturnLine,
    Service,
    StaffProfile,
    StockMovement,
    StockReceipt,
    Supplier,
    Ward,
)
from .services.numbering import next_number


def _login_throttle_key(request, username):
    return f"login-fail:{request.META.get('REMOTE_ADDR', 'unknown')}:{(username or '').strip().lower()}"


class HospitalLoginView(LoginView):
    def dispatch(self, request, *args, **kwargs):
        username = (request.POST.get("username", "") or "").strip().lower()
        if (
            request.method == "POST"
            and cache.get(_login_throttle_key(request, username), 0) >= 5
        ):
            response = HttpResponse(
                "Too many failed login attempts. Please wait a few minutes and try again.",
                status=429,
            )
            return response
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        username = (self.request.POST.get("username", "") or "").strip().lower()
        key = _login_throttle_key(self.request, username)
        attempts = cache.get(key, 0) + 1
        cache.set(key, attempts, timeout=600)
        if attempts >= 5:
            return HttpResponse(
                "Too many failed login attempts. Please wait a few minutes and try again.",
                status=429,
            )
        return super().form_invalid(form)

    def form_valid(self, form):
        username = (self.request.POST.get("username", "") or "").strip().lower()
        cache.delete(_login_throttle_key(self.request, username))
        return super().form_valid(form)


def home(request):
    hospital = HospitalSettings.objects.filter(pk=1).only("name").first()
    context = {"hospital": hospital}
    user = request.user

    if user.is_authenticated:
        today = timezone.localdate()
        is_reception = _has_role(user, "Reception")
        is_doctor = _has_role(user, "Doctor")
        is_pharmacy = _has_role(user, "Pharmacy")
        is_admin = _has_role(user, "Administrator")

        context["is_reception"] = is_reception
        context["is_doctor"] = is_doctor
        context["is_pharmacy"] = is_pharmacy
        context["is_admin"] = is_admin

        if is_reception:
            context["reception_today_appointments"] = Appointment.objects.filter(
                scheduled_at__date=today
            ).count()
            context["reception_waiting_queue"] = Appointment.objects.filter(
                scheduled_at__date=today, status=Appointment.Status.CHECKED_IN
            ).count()
            context["reception_today_collections"] = Payment.objects.filter(
                received_at__date=today
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        if is_doctor:
            doctor_profile = StaffProfile.objects.filter(user=user).first()
            if doctor_profile:
                context["doctor_today_appointments"] = Appointment.objects.filter(
                    doctor=doctor_profile, scheduled_at__date=today
                ).count()
                context["doctor_waiting_patients"] = Appointment.objects.filter(
                    doctor=doctor_profile,
                    scheduled_at__date=today,
                    status=Appointment.Status.CHECKED_IN,
                ).count()

        if is_pharmacy:
            context["pharmacy_issued_prescriptions"] = Prescription.objects.filter(
                status=Prescription.Status.ISSUED
            ).count()
            context["pharmacy_low_stock_batches"] = MedicineBatch.objects.filter(
                quantity_on_hand__lt=10, is_quarantined=False
            ).count()
            context["pharmacy_expired_batches"] = MedicineBatch.objects.filter(
                expiry_date__lt=today
            ).count()

        if is_admin:
            context["admin_total_patients"] = Patient.objects.filter(
                archived_at__isnull=True
            ).count()
            context["admin_today_collections"] = Payment.objects.filter(
                received_at__date=today
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            context["admin_today_refunds"] = Refund.objects.filter(
                created_at__date=today, status=Refund.Status.ISSUED
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            context["admin_unsettled_invoices"] = Invoice.objects.filter(
                status=Invoice.Status.ISSUED
            ).count()

    return render(request, "core/home.html", context)


def health(request):
    try:
        from django.db import connection
        connection.ensure_connection()
        return JsonResponse({"status": "ok", "database": "connected"})
    except Exception as e:
        return JsonResponse({"status": "error", "database": str(e)}, status=503)


def _has_role(user, role):
    return user.groups.filter(name=role).exists()


def _patient_read_queryset(user):
    if _has_role(user, "Reception") and StaffProfile.objects.filter(user=user).exists():
        return Patient.objects.filter(archived_at__isnull=True)
    if _has_role(user, "Doctor"):
        return doctor_patient_queryset(user).filter(archived_at__isnull=True)
    raise PermissionDenied


def _financial_actor(request):
    if not _has_role(request.user, "Administrator"):
        raise PermissionDenied
    return get_object_or_404(StaffProfile, user=request.user)


def _invoice_outstanding(invoice):
    paid = invoice.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    refunded = Refund.objects.filter(
        payment__invoice=invoice, status=Refund.Status.ISSUED
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    adjusted = invoice.adjustments.aggregate(total=Sum("amount"))["total"] or Decimal(
        "0.00"
    )
    return invoice.total + adjusted - paid + refunded


def _audit_financial_change(request, action, target, details):
    AuditEvent.objects.create(
        actor=StaffProfile.objects.filter(user=request.user).first(),
        action=action,
        target_type=target.__class__.__name__.lower(),
        target_id=str(target.pk),
        details=details,
    )


def _request_key(request):
    try:
        return uuid.UUID(request.POST.get("request_key", ""))
    except (AttributeError, TypeError, ValueError):
        return None


@permission_required("core.add_invoice", raise_exception=True)
def invoice_create(request):
    is_reception = _has_role(request.user, "Reception")
    is_admin = _has_role(request.user, "Administrator")
    if (
        not (is_reception or is_admin)
        or not StaffProfile.objects.filter(user=request.user).exists()
    ):
        raise PermissionDenied
    if request.method != "POST":
        return HttpResponseBadRequest("Invoices require POST.")

    patient = get_object_or_404(
        Patient.objects.filter(archived_at__isnull=True),
        pk=request.POST.get("patient"),
    )
    service = get_object_or_404(Service, pk=request.POST.get("service"))
    try:
        quantity = Decimal(request.POST.get("quantity", "1"))
        unit_price = Decimal(
            request.POST.get("unit_price", service.current_charge or 0)
        )
        discount = Decimal(request.POST.get("discount_amount", "0.00"))
    except InvalidOperation:
        return HttpResponseBadRequest("Invoice amounts must be valid numbers.")
    if (
        not quantity.is_finite()
        or not unit_price.is_finite()
        or not discount.is_finite()
        or quantity <= 0
        or unit_price < 0
        or discount < 0
    ):
        return HttpResponseBadRequest("Invoice amounts are outside the valid range.")
    if discount and not is_admin:
        raise PermissionDenied
    reason = request.POST.get("reason", "").strip()
    if discount and not reason:
        return HttpResponseBadRequest("A reason is required for a discount.")
    description = request.POST.get("description", service.name).strip() or service.name
    subtotal = (quantity * unit_price).quantize(Decimal("0.01"))
    if discount > subtotal:
        return HttpResponseBadRequest("Discount cannot exceed the invoice subtotal.")
    line_total = subtotal - discount

    with transaction.atomic():
        invoice = Invoice.objects.create(
            number=next_number("INVOICE"),
            patient=patient,
            status=Invoice.Status.ISSUED,
            subtotal=subtotal,
            discount_total=discount,
            tax_total=Decimal("0.00"),
            total=line_total,
            issued_at=timezone.now(),
            created_by=StaffProfile.objects.get(user=request.user),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            service=service,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            discount_amount=discount,
            line_total=line_total,
        )
        if discount:
            _audit_financial_change(
                request,
                "financial.discount_applied",
                invoice,
                {"amount": str(discount), "reason": reason},
            )
    messages.success(request, f"Invoice {invoice.number} created.")
    return redirect("invoice_detail", pk=invoice.pk)


def invoice_detail(request, pk):
    if (
        not (
            _has_role(request.user, "Reception")
            or _has_role(request.user, "Administrator")
        )
        or not StaffProfile.objects.filter(user=request.user).exists()
    ):
        raise PermissionDenied
    invoice = get_object_or_404(
        Invoice.objects.select_related("patient").prefetch_related(
            "lines", "payments__method", "adjustments", "payments__refunds"
        ),
        pk=pk,
    )
    pharmacy_returns = (
        PharmacyReturn.objects.filter(
            Q(lines__sale_line__sale__invoice=invoice)
            | Q(lines__dispensing_line__dispensing__invoice=invoice),
            status=PharmacyReturn.Status.PENDING,
        )
        .distinct()
        .prefetch_related("lines")
    )
    for pharmacy_return in pharmacy_returns:
        pharmacy_return.refund_total = pharmacy_return.lines.aggregate(
            total=Sum("refund_amount")
        )["total"] or Decimal("0.00")
    return render(
        request,
        "core/billing/invoice_detail.html",
        {
            "invoice": invoice,
            "outstanding": _invoice_outstanding(invoice),
            "is_admin": _has_role(request.user, "Administrator"),
            "is_reception": _has_role(request.user, "Reception"),
            "payment_methods": PaymentMethod.objects.filter(is_active=True),
            "can_back_to_patient": _has_role(request.user, "Reception")
            and invoice.patient_id is not None,
            "pharmacy_returns": pharmacy_returns,
            "can_void": invoice.status == Invoice.Status.ISSUED
            and not invoice.payments.exists()
            and not invoice.adjustments.exists(),
        },
    )


@permission_required("core.view_invoice", raise_exception=True)
def invoice_list(request):
    if (
        not (
            _has_role(request.user, "Reception")
            or _has_role(request.user, "Administrator")
        )
        or not StaffProfile.objects.filter(user=request.user).exists()
    ):
        raise PermissionDenied
    invoices = Invoice.objects.select_related("patient").order_by("-created_at")
    query = request.GET.get("q", "").strip()
    if query:
        invoices = invoices.filter(
            Q(number__icontains=query)
            | Q(patient__mrn__icontains=query)
            | Q(patient__full_name__icontains=query)
        )
    invoices = list(invoices)
    for invoice in invoices:
        invoice.balance = _invoice_outstanding(invoice)
    return render(
        request,
        "core/billing/invoice_list.html",
        {"invoices": invoices, "query": query},
    )


@permission_required("core.add_payment", raise_exception=True)
def payment_create(request, pk):
    if (
        not _has_role(request.user, "Reception")
        or not StaffProfile.objects.filter(user=request.user).exists()
    ):
        raise PermissionDenied

    if request.method != "POST":
        return HttpResponseBadRequest("Payments require POST.")

    method = get_object_or_404(
        PaymentMethod.objects.filter(is_active=True), pk=request.POST.get("method")
    )
    try:
        amount = Decimal(request.POST.get("amount", "0"))
    except InvalidOperation:
        return HttpResponseBadRequest("Payment amount must be a valid number.")
    if not amount.is_finite() or amount <= 0:
        return HttpResponseBadRequest("Payment amount must be positive.")

    with transaction.atomic():
        invoice = get_object_or_404(Invoice.objects.select_for_update(), pk=pk)
        if invoice.status != Invoice.Status.ISSUED or amount > _invoice_outstanding(
            invoice
        ):
            return HttpResponseBadRequest("Payment exceeds the invoice balance.")

        Payment.objects.create(
            receipt_number=next_number("RECEIPT"),
            invoice=invoice,
            method=method,
            amount=amount,
            reference=request.POST.get("reference", "").strip(),
            received_by=StaffProfile.objects.get(user=request.user),
            received_at=timezone.now(),
        )
    messages.success(request, f"Payment of {amount} recorded.")
    return redirect("invoice_detail", pk=invoice.pk)


@permission_required("core.add_adjustment", raise_exception=True)
def invoice_adjustment(request, pk):
    actor = _financial_actor(request)
    if request.method != "POST":
        return HttpResponseBadRequest("Adjustments require POST.")
    reason = request.POST.get("reason", "").strip()
    if not reason:
        return HttpResponseBadRequest("A reason is required.")
    try:
        amount = Decimal(request.POST.get("amount", "0"))
    except InvalidOperation:
        return HttpResponseBadRequest("Adjustment amount must be a valid number.")
    kind = request.POST.get("kind", "adjustment")
    if not amount.is_finite() or amount == 0 or kind not in {"discount", "adjustment"}:
        return HttpResponseBadRequest("Adjustment amount or type is invalid.")
    if kind == "discount":
        if amount < 0:
            return HttpResponseBadRequest("Discount amount must be positive.")
        amount = -amount

    with transaction.atomic():
        invoice = get_object_or_404(Invoice.objects.select_for_update(), pk=pk)
        if (
            invoice.status != Invoice.Status.ISSUED
            or _invoice_outstanding(invoice) + amount < 0
        ):
            return HttpResponseBadRequest("Adjustment would make the balance invalid.")
        adjustment = Adjustment.objects.create(
            invoice=invoice,
            amount=amount,
            reason=reason,
            approved_by=actor,
        )
        _audit_financial_change(
            request,
            "financial.discount_applied"
            if kind == "discount"
            else "financial.adjustment_created",
            adjustment,
            {"invoice_id": invoice.pk, "amount": str(amount), "reason": reason},
        )
    messages.success(request, f"Adjustment of {amount} applied.")
    return redirect("invoice_detail", pk=invoice.pk)


@permission_required("core.add_refund", raise_exception=True)
def invoice_refund(request, pk):
    actor = _financial_actor(request)
    if request.method != "POST":
        return HttpResponseBadRequest("Refunds require POST.")
    reason = request.POST.get("reason", "").strip()
    if not reason:
        return HttpResponseBadRequest("A reason is required.")
    try:
        amount = Decimal(request.POST.get("amount", "0"))
    except InvalidOperation:
        return HttpResponseBadRequest("Refund amount must be a valid number.")
    if not amount.is_finite() or amount <= 0:
        return HttpResponseBadRequest("Refund amount must be positive.")
    payment_id = request.POST.get("payment")
    pharmacy_return_id = request.POST.get("pharmacy_return")

    with transaction.atomic():
        invoice = get_object_or_404(Invoice.objects.select_for_update(), pk=pk)
        payment = get_object_or_404(
            Payment.objects.select_for_update().filter(invoice=invoice), pk=payment_id
        )
        already_refunded = payment.refunds.filter(
            status=Refund.Status.ISSUED
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        pharmacy_return = None
        if pharmacy_return_id:
            pharmacy_return = get_object_or_404(
                PharmacyReturn.objects.select_for_update(),
                pk=pharmacy_return_id,
                status=PharmacyReturn.Status.PENDING,
            )
            return_lines = ReturnLine.objects.filter(
                pharmacy_return=pharmacy_return
            ).filter(
                Q(sale_line__sale__invoice=invoice)
                | Q(dispensing_line__dispensing__invoice=invoice)
            )
            if not return_lines.exists():
                raise PermissionDenied
            return_total = return_lines.aggregate(total=Sum("refund_amount"))[
                "total"
            ] or Decimal("0.00")
            if amount != return_total:
                return HttpResponseBadRequest(
                    "Refund amount must match the linked return request."
                )
        if (
            invoice.status != Invoice.Status.ISSUED
            or already_refunded + amount > payment.amount
        ):
            return HttpResponseBadRequest(
                "Refund exceeds the refundable payment balance."
            )
        refund = Refund.objects.create(
            payment=payment,
            amount=amount,
            reason=reason,
            status=Refund.Status.ISSUED,
            requested_by=actor,
            approved_by=actor,
            pharmacy_return=pharmacy_return,
        )
        if pharmacy_return:
            pharmacy_return.status = PharmacyReturn.Status.APPROVED
            pharmacy_return.save(update_fields=("status", "updated_at"))
        _audit_financial_change(
            request,
            "financial.refund_issued",
            refund,
            {
                "invoice_id": invoice.pk,
                "payment_id": payment.pk,
                "pharmacy_return_id": pharmacy_return.pk if pharmacy_return else None,
                "amount": str(amount),
                "reason": reason,
            },
        )
    return redirect("invoice_detail", pk=invoice.pk)


@permission_required("core.add_refund", raise_exception=True)
def pharmacy_return_reject(request, pk):
    actor = _financial_actor(request)
    if request.method != "POST":
        return HttpResponseBadRequest("Return decisions require POST.")
    reason = request.POST.get("reason", "").strip()
    if not reason:
        return HttpResponseBadRequest("A rejection reason is required.")
    with transaction.atomic():
        pharmacy_return = get_object_or_404(
            PharmacyReturn.objects.select_for_update(),
            pk=pk,
            status=PharmacyReturn.Status.PENDING,
        )
        if hasattr(pharmacy_return, "refund"):
            return HttpResponseBadRequest("A refunded return cannot be rejected.")
        pharmacy_return.status = PharmacyReturn.Status.REJECTED
        pharmacy_return.save(update_fields=("status", "updated_at"))
        AuditEvent.objects.create(
            actor=actor,
            action="pharmacy.return_rejected",
            target_type="pharmacyreturn",
            target_id=str(pharmacy_return.pk),
            details={"reason": reason},
        )
        sale_invoice_id = (
            pharmacy_return.lines.filter(sale_line__isnull=False)
            .values_list("sale_line__sale__invoice_id", flat=True)
            .first()
        )
        dispensing_invoice_id = (
            pharmacy_return.lines.filter(dispensing_line__isnull=False)
            .values_list("dispensing_line__dispensing__invoice_id", flat=True)
            .first()
        )
        invoice_id = sale_invoice_id or dispensing_invoice_id
    if invoice_id:
        return redirect("invoice_detail", pk=invoice_id)
    return redirect("pharmacy_prescription_list")


@permission_required("core.void_invoice", raise_exception=True)
def invoice_void(request, pk):
    _financial_actor(request)
    if request.method != "POST":
        return HttpResponseBadRequest("Invoice voids require POST.")
    reason = request.POST.get("reason", "").strip()
    if not reason:
        return HttpResponseBadRequest("A reason is required.")

    with transaction.atomic():
        invoice = get_object_or_404(Invoice.objects.select_for_update(), pk=pk)
        if (
            invoice.status != Invoice.Status.ISSUED
            or invoice.payments.exists()
            or invoice.adjustments.exists()
        ):
            return HttpResponseBadRequest("Only unsettled invoices can be voided.")
        invoice.status = Invoice.Status.VOIDED
        invoice.save(update_fields=("status", "updated_at"))
        _audit_financial_change(
            request,
            "financial.invoice_voided",
            invoice,
            {"reason": reason},
        )
    messages.success(request, f"Invoice {invoice.number} voided.")
    return redirect("invoice_detail", pk=invoice.pk)


def _audit_patient_change(request, patient, action, changed_fields):
    actor = StaffProfile.objects.filter(user=request.user).first()
    AuditEvent.objects.create(
        actor=actor,
        action=action,
        target_type="patient",
        target_id=str(patient.pk),
        details={"changed_fields": sorted(changed_fields)},
    )


@permission_required("core.view_patient", raise_exception=True)
def patient_list(request):
    patients = _patient_read_queryset(request.user)
    query = request.GET.get("q", "").strip()
    if query:
        patients = patients.filter(
            Q(mrn__icontains=query)
            | Q(full_name__icontains=query)
            | Q(phone__icontains=query)
        )
    return render(
        request,
        "core/patients/list.html",
        {
            "patients": patients.order_by("full_name", "mrn"),
            "query": query,
            "can_register": _has_role(request.user, "Reception"),
        },
    )


@permission_required("core.add_patient", raise_exception=True)
def patient_create(request):
    if (
        not _has_role(request.user, "Reception")
        or not StaffProfile.objects.filter(user=request.user).exists()
    ):
        raise PermissionDenied

    form = PatientForm(request.POST or None)
    duplicates = Patient.objects.none()
    if request.method == "POST" and form.is_valid():
        phone = form.cleaned_data["phone"]
        if phone:
            duplicates = Patient.objects.filter(
                archived_at__isnull=True,
                full_name__iexact=form.cleaned_data["full_name"],
                phone__iexact=phone,
            ).order_by("full_name", "mrn")

        if not duplicates.exists() or request.POST.get("confirm_duplicate") == "yes":
            with transaction.atomic():
                patient = form.save(commit=False)
                patient.mrn = next_number("PATIENT")
                patient.save()
                _audit_patient_change(
                    request, patient, "patient.created", form.changed_data
                )
            messages.success(
                request, f"Patient {patient.full_name} registered successfully."
            )
            return redirect("patient_detail", pk=patient.pk)

    return render(
        request,
        "core/patients/form.html",
        {"form": form, "duplicates": duplicates, "creating": True},
    )


@permission_required("core.view_patient", raise_exception=True)
def patient_detail(request, pk):
    patient = get_object_or_404(_patient_read_queryset(request.user), pk=pk)
    can_bill = _has_role(request.user, "Reception")
    can_upload_docs = _has_role(request.user, "Reception") or _has_role(
        request.user, "Administrator"
    ) or _has_role(request.user, "Doctor")
    return render(
        request,
        "core/patients/detail.html",
        {
            "patient": patient,
            "can_edit": _has_role(request.user, "Reception"),
            "can_view_clinical": _has_role(request.user, "Doctor"),
            "can_bill": can_bill,
            "can_upload_docs": can_upload_docs,
            "document_form": PatientDocumentForm() if can_upload_docs else None,
            "documents": patient.documents.all(),
            "invoices": patient.invoices.order_by("-created_at")
            if can_bill
            else Invoice.objects.none(),
            "services": Service.objects.filter(is_active=True)
            if can_bill
            else Service.objects.none(),
        },
    )



@permission_required("core.change_patient", raise_exception=True)
def patient_update(request, pk):
    if (
        not _has_role(request.user, "Reception")
        or not StaffProfile.objects.filter(user=request.user).exists()
    ):
        raise PermissionDenied
    patient = get_object_or_404(Patient.objects.filter(archived_at__isnull=True), pk=pk)
    form = PatientForm(request.POST or None, instance=patient)
    if request.method == "POST" and form.is_valid():
        changed_fields = form.changed_data
        if changed_fields:
            with transaction.atomic():
                patient = form.save()
                _audit_patient_change(
                    request, patient, "patient.demographics_updated", changed_fields
                )
        messages.success(request, f"Patient {patient.full_name} updated successfully.")
        return redirect("patient_detail", pk=patient.pk)

    return render(
        request,
        "core/patients/form.html",
        {"form": form, "creating": False, "patient": patient},
    )


@permission_required("core.add_patientdocument", raise_exception=True)
def patient_document_upload(request, pk):
    patient = get_object_or_404(Patient.objects.filter(archived_at__isnull=True), pk=pk)
    if not (
        _has_role(request.user, "Reception")
        or _has_role(request.user, "Doctor")
        or _has_role(request.user, "Administrator")
    ):
        raise PermissionDenied

    if request.method == "POST":
        form = PatientDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                doc = form.save(commit=False)
                doc.patient = patient
                doc.uploaded_by = StaffProfile.objects.filter(user=request.user).first()
                doc.save()
                _audit_patient_change(
                    request,
                    patient,
                    "patient.document_uploaded",
                    [f"doc_type:{doc.document_type}", f"title:{doc.title}"],
                )
            messages.success(request, f"Document '{doc.title}' uploaded successfully.")
        else:
            messages.error(request, "Failed to upload document. Please check the file and try again.")
    return redirect("patient_detail", pk=patient.pk)



def _appointment_read_queryset(user):
    if _has_role(user, "Reception") and StaffProfile.objects.filter(user=user).exists():
        return Appointment.objects.all()
    if _has_role(user, "Doctor"):
        return Appointment.objects.filter(doctor__user=user)
    raise PermissionDenied


def _audit_appointment_change(request, appointment, action, details):
    actor = StaffProfile.objects.filter(user=request.user).first()
    AuditEvent.objects.create(
        actor=actor,
        action=action,
        target_type="appointment",
        target_id=str(appointment.pk),
        details=details,
    )


@permission_required("core.view_appointment", raise_exception=True)
def appointment_list(request):
    raw_day = request.GET.get("date", "")
    selected_day = parse_date(raw_day) if raw_day else timezone.localdate()
    if selected_day is None:
        return HttpResponseBadRequest("Invalid appointment date.")

    appointments = _appointment_read_queryset(request.user).filter(
        scheduled_at__date=selected_day
    )
    queue = appointments.filter(status=Appointment.Status.CHECKED_IN).order_by(
        "checked_in_at", "pk"
    )
    summary = {
        "total": appointments.count(),
        "scheduled": appointments.filter(status=Appointment.Status.SCHEDULED).count(),
        "in_progress": appointments.filter(
            status=Appointment.Status.IN_PROGRESS
        ).count(),
        "completed": appointments.filter(status=Appointment.Status.COMPLETED).count(),
    }
    return render(
        request,
        "core/appointments/list.html",
        {
            "appointments": appointments.select_related(
                "patient", "doctor__user", "visit_type"
            ).order_by("scheduled_at", "pk"),
            "queue": queue.select_related("patient", "doctor__user", "visit_type"),
            "selected_day": selected_day,
            "today": timezone.localdate(),
            "previous_day": selected_day - timedelta(days=1),
            "next_day": selected_day + timedelta(days=1),
            "summary": summary,
            "is_reception": _has_role(request.user, "Reception"),
            "is_doctor": _has_role(request.user, "Doctor"),
        },
    )


@permission_required("core.add_appointment", raise_exception=True)
def appointment_create(request):
    if (
        not _has_role(request.user, "Reception")
        or not StaffProfile.objects.filter(user=request.user).exists()
    ):
        raise PermissionDenied
    form = AppointmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                doctor = form.cleaned_data["doctor"]
                StaffProfile.objects.select_for_update().get(pk=doctor.pk)
                if appointment_slot_conflicts(
                    doctor, form.cleaned_data["scheduled_at"]
                ):
                    form.add_error(
                        "scheduled_at",
                        "This doctor already has an overlapping active appointment.",
                    )
                else:
                    appointment = form.save()
                    _audit_appointment_change(
                        request,
                        appointment,
                        "appointment.created",
                        {"status": appointment.status},
                    )
        except IntegrityError:
            form.add_error(
                "scheduled_at",
                "This doctor already has an overlapping active appointment.",
            )
        else:
            if not form.errors:
                messages.success(request, "Appointment booked successfully.")
                return redirect("appointment_list")
    return render(
        request,
        "core/appointments/form.html",
        {"form": form, "creating": True},
    )


@permission_required("core.change_appointment", raise_exception=True)
def appointment_reschedule(request, pk):
    if (
        not _has_role(request.user, "Reception")
        or not StaffProfile.objects.filter(user=request.user).exists()
    ):
        raise PermissionDenied
    appointment = get_object_or_404(
        Appointment.objects.filter(status=Appointment.Status.SCHEDULED), pk=pk
    )
    form = AppointmentForm(request.POST or None, instance=appointment)
    if request.method == "POST" and form.is_valid():
        changed_fields = form.changed_data
        try:
            with transaction.atomic():
                doctor = form.cleaned_data["doctor"]
                StaffProfile.objects.select_for_update().get(pk=doctor.pk)
                if appointment_slot_conflicts(
                    doctor,
                    form.cleaned_data["scheduled_at"],
                    exclude_pk=appointment.pk,
                ):
                    form.add_error(
                        "scheduled_at",
                        "This doctor already has an overlapping active appointment.",
                    )
                else:
                    appointment = form.save()
                    _audit_appointment_change(
                        request,
                        appointment,
                        "appointment.rescheduled",
                        {"changed_fields": sorted(changed_fields)},
                    )
        except IntegrityError:
            form.add_error(
                "scheduled_at",
                "This doctor already has an overlapping active appointment.",
            )
        else:
            if not form.errors:
                messages.success(request, "Appointment rescheduled successfully.")
                return redirect("appointment_list")
    return render(
        request,
        "core/appointments/form.html",
        {"form": form, "creating": False, "appointment": appointment},
    )


@permission_required("core.change_appointment", raise_exception=True)
def appointment_transition(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("Appointment actions require POST.")
    appointments = _appointment_read_queryset(request.user)
    appointment = get_object_or_404(appointments, pk=pk)
    action = request.POST.get("action", "")
    reception_transitions = {
        (Appointment.Status.SCHEDULED, "check_in"): Appointment.Status.CHECKED_IN,
        (Appointment.Status.SCHEDULED, "cancel"): Appointment.Status.CANCELLED,
        (Appointment.Status.SCHEDULED, "no_show"): Appointment.Status.NO_SHOW,
        (Appointment.Status.CHECKED_IN, "cancel"): Appointment.Status.CANCELLED,
    }
    doctor_transitions = {
        (Appointment.Status.CHECKED_IN, "start"): Appointment.Status.IN_PROGRESS,
        (Appointment.Status.IN_PROGRESS, "complete"): Appointment.Status.COMPLETED,
    }
    transitions = (
        reception_transitions
        if _has_role(request.user, "Reception")
        else doctor_transitions
        if _has_role(request.user, "Doctor")
        else {}
    )
    previous_status = appointment.status
    next_status = transitions.get((previous_status, action))
    if next_status is None:
        return HttpResponseBadRequest("Invalid appointment status transition.")

    with transaction.atomic():
        appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
        if appointment.status != previous_status:
            return HttpResponseBadRequest(
                "Appointment status changed; refresh and retry."
            )
        appointment.status = next_status
        timestamp = timezone.now()
        update_fields = ["status", "updated_at"]
        if action == "check_in":
            appointment.checked_in_at = timestamp
            update_fields.append("checked_in_at")
        elif action == "start":
            appointment.started_at = timestamp
            update_fields.append("started_at")
        elif action == "complete":
            appointment.completed_at = timestamp
            update_fields.append("completed_at")
        elif action == "cancel":
            appointment.cancelled_at = timestamp
            update_fields.append("cancelled_at")
        elif action == "no_show":
            appointment.no_show_at = timestamp
            update_fields.append("no_show_at")
        appointment.save(update_fields=update_fields)
        _audit_appointment_change(
            request,
            appointment,
            "appointment.status_changed",
            {"from": previous_status, "to": next_status},
        )
    action_labels = {
        "check_in": "Patient checked in.",
        "start": "Consultation started.",
        "complete": "Appointment completed.",
        "cancel": "Appointment cancelled.",
        "no_show": "Appointment marked as no-show.",
    }
    messages.success(request, action_labels.get(action, "Appointment updated."))
    return redirect("appointment_list")


def _doctor_profile(user):
    if not _has_role(user, "Doctor"):
        raise PermissionDenied
    profile = StaffProfile.objects.filter(user=user).first()
    if profile is None:
        raise PermissionDenied
    return profile


def _audit_clinical_access(request, action, target_type, target_id):
    actor = StaffProfile.objects.filter(user=request.user).first()
    AuditEvent.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        details={},
    )


@permission_required("core.view_consultation", raise_exception=True)
def clinical_history(request, patient_id):
    profile = _doctor_profile(request.user)
    patient = get_object_or_404(
        doctor_patient_queryset(request.user).filter(archived_at__isnull=True),
        pk=patient_id,
    )
    consultations = Consultation.objects.filter(
        patient=patient, doctor=profile
    ).order_by("-created_at")
    _audit_clinical_access(request, "clinical.history_viewed", "patient", patient.pk)
    return render(
        request,
        "core/clinical/history.html",
        {"patient": patient, "consultations": consultations},
    )


@permission_required("core.add_consultation", raise_exception=True)
def consultation_create(request, appointment_id):
    profile = _doctor_profile(request.user)
    appointment = get_object_or_404(
        Appointment.objects.filter(
            doctor=profile, status=Appointment.Status.IN_PROGRESS
        ).select_related("patient"),
        pk=appointment_id,
    )
    existing = Consultation.objects.filter(appointment=appointment).first()
    if existing:
        return redirect("consultation_detail", pk=existing.pk)

    form = ConsultationForm(request.POST or None)
    item_formset = PrescriptionItemFormSet(request.POST or None, prefix="items")
    if request.method == "POST" and form.is_valid() and item_formset.is_valid():
        try:
            with transaction.atomic():
                consultation = form.save(commit=False)
                consultation.appointment = appointment
                consultation.patient = appointment.patient
                consultation.doctor = profile
                consultation.save()
                _audit_clinical_access(
                    request,
                    "clinical.consultation_created",
                    "consultation",
                    consultation.pk,
                )

                if any(item_form.has_changed() for item_form in item_formset.forms):
                    prescription = Prescription.objects.create(
                        number=next_number("PRESCRIPTION"),
                        consultation=consultation,
                        patient=appointment.patient,
                        doctor=profile,
                        status=Prescription.Status.ISSUED,
                        issued_at=timezone.now(),
                    )
                    item_formset.instance = prescription
                    item_formset.save()
                    _audit_clinical_access(
                        request,
                        "clinical.prescription_issued",
                        "prescription",
                        prescription.pk,
                    )
        except IntegrityError:
            existing = Consultation.objects.filter(appointment=appointment).first()
            if existing is None:
                raise
            return redirect("consultation_detail", pk=existing.pk)
        messages.success(request, "Consultation saved successfully.")
        return redirect("consultation_detail", pk=consultation.pk)

    return render(
        request,
        "core/clinical/consultation_form.html",
        {
            "appointment": appointment,
            "form": form,
            "item_formset": item_formset,
        },
    )


@permission_required("core.view_consultation", raise_exception=True)
def consultation_detail(request, pk):
    profile = _doctor_profile(request.user)
    consultation = get_object_or_404(
        Consultation.objects.select_related("patient", "doctor__user", "appointment"),
        pk=pk,
        doctor=profile,
    )
    prescriptions = consultation.prescriptions.prefetch_related(
        "items__medicine"
    ).order_by("created_at")
    _audit_clinical_access(
        request, "clinical.consultation_viewed", "consultation", consultation.pk
    )
    return render(
        request,
        "core/clinical/consultation_detail.html",
        {"consultation": consultation, "prescriptions": prescriptions},
    )


@permission_required("core.view_prescription", raise_exception=True)
def prescription_print(request, pk):
    if _has_role(request.user, "Doctor"):
        profile = _doctor_profile(request.user)
        prescriptions = Prescription.objects.filter(doctor=profile)
    elif _has_role(request.user, "Pharmacy"):
        prescriptions = Prescription.objects.filter(status=Prescription.Status.ISSUED)
    else:
        raise PermissionDenied
    prescription = get_object_or_404(
        prescriptions.select_related("patient", "doctor__user", "consultation"),
        pk=pk,
    )
    _audit_clinical_access(
        request, "clinical.prescription_printed", "prescription", prescription.pk
    )
    return render(
        request,
        "core/clinical/prescription_print.html",
        {
            "prescription": prescription,
            "items": prescription.items.select_related("medicine"),
        },
    )


@permission_required("core.add_stockreceipt", raise_exception=True)
def stock_receipt_create(request):
    if not _has_role(request.user, "Pharmacy"):
        raise PermissionDenied
    if request.method != "POST":
        return HttpResponseBadRequest("Stock receipts require POST.")

    request_key = _request_key(request)
    if request_key is None:
        return HttpResponseBadRequest("A valid request key is required.")

    supplier = get_object_or_404(Supplier, pk=request.POST.get("supplier"))
    medicine = get_object_or_404(Medicine, pk=request.POST.get("medicine"))
    try:
        quantity_received = Decimal(request.POST.get("quantity_received", "0"))
        purchase_price = Decimal(request.POST.get("purchase_price", "0.00"))
        sale_price = Decimal(request.POST.get("sale_price", "0.00"))
    except InvalidOperation:
        return HttpResponseBadRequest("Receipt amounts must be valid numbers.")
    if (
        not quantity_received.is_finite()
        or not purchase_price.is_finite()
        or not sale_price.is_finite()
        or quantity_received <= 0
        or purchase_price < 0
        or sale_price < 0
    ):
        return HttpResponseBadRequest("Receipt amounts are outside the valid range.")
    if StockMovement.objects.filter(request_key=request_key).exists():
        return redirect("pharmacy_prescription_list")

    if quantity_received <= 0:
        return HttpResponseBadRequest("Quantity received must be positive.")

    expiry_date = parse_date(request.POST.get("expiry_date", ""))
    if not expiry_date:
        return HttpResponseBadRequest("A valid expiry date is required.")

    with transaction.atomic():
        receipt = StockReceipt.objects.create(
            number=next_number("STOCK_RECEIPT"),
            supplier=supplier,
            supplier_reference=request.POST.get("supplier_reference", "").strip(),
            received_at=timezone.now(),
            received_by=StaffProfile.objects.get(user=request.user),
        )
        batch = MedicineBatch.objects.create(
            medicine=medicine,
            receipt=receipt,
            batch_number=request.POST.get("batch_number", "").strip()
            or "BATCH-UNKNOWN",
            expiry_date=expiry_date,
            purchase_price=purchase_price,
            sale_price=sale_price,
            quantity_received=quantity_received,
            quantity_on_hand=quantity_received,
        )
        StockMovement.objects.create(
            batch=batch,
            kind=StockMovement.Kind.RECEIPT,
            quantity_delta=quantity_received,
            quantity_before=Decimal("0"),
            quantity_after=quantity_received,
            reference_type="stock_receipt",
            reference_id=str(receipt.pk),
            request_key=request_key,
            actor=StaffProfile.objects.get(user=request.user),
        )
    return redirect("pharmacy_prescription_list")


@permission_required("core.add_pharmacysale", raise_exception=True)
def pharmacy_sale_create(request):
    if not _has_role(request.user, "Pharmacy"):
        raise PermissionDenied
    if request.method != "POST":
        return HttpResponseBadRequest("Counter sales require POST.")
    request_key = _request_key(request)
    if request_key is None:
        return HttpResponseBadRequest("A valid request key is required.")
    existing = StockMovement.objects.filter(request_key=request_key).first()
    if existing:
        if existing.kind == StockMovement.Kind.SALE:
            return redirect("pharmacy_sale_detail", pk=existing.reference_id)
        return HttpResponse("Request key already used.", status=409)
    try:
        quantity = Decimal(request.POST.get("quantity", "0"))
    except InvalidOperation:
        return HttpResponseBadRequest("Sale quantity must be a valid number.")
    if not quantity.is_finite() or quantity <= 0:
        return HttpResponseBadRequest("Sale quantity must be positive.")

    with transaction.atomic():
        batch = get_object_or_404(
            MedicineBatch.objects.select_for_update().select_related("medicine"),
            pk=request.POST.get("batch"),
        )
        medicine = batch.medicine
        if not medicine.is_active or not medicine.is_otc:
            return HttpResponseBadRequest("This medicine is not approved for OTC sale.")
        if batch.expiry_date < timezone.localdate():
            return HttpResponseBadRequest("Expired stock cannot be sold.")
        if batch.is_quarantined:
            return HttpResponseBadRequest("Quarantined stock cannot be sold.")
        if batch.quantity_on_hand < quantity:
            return HttpResponseBadRequest("Insufficient stock available for sale.")
        if StockMovement.objects.filter(request_key=request_key).exists():
            return redirect("pharmacy_prescription_list")

        actor = StaffProfile.objects.get(user=request.user)
        total = (batch.sale_price * quantity).quantize(Decimal("0.01"))
        invoice = Invoice.objects.create(
            number=next_number("INVOICE"),
            patient=None,
            status=Invoice.Status.ISSUED,
            subtotal=total,
            tax_total=Decimal("0.00"),
            total=total,
            issued_at=timezone.now(),
            created_by=actor,
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            description=f"{medicine.generic_name} {medicine.strength}".strip(),
            quantity=quantity,
            unit_price=batch.sale_price,
            discount_amount=Decimal("0.00"),
            line_total=total,
        )
        sale = PharmacySale.objects.create(
            number=next_number("PHARMACY_SALE"),
            invoice=invoice,
            status=PharmacySale.Status.ISSUED,
            sold_at=timezone.now(),
            sold_by=actor,
        )
        line = PharmacySaleLine.objects.create(
            sale=sale,
            batch=batch,
            quantity=quantity,
            unit_price=batch.sale_price,
            line_total=total,
        )
        before = batch.quantity_on_hand
        batch.quantity_on_hand = before - quantity
        batch.save(update_fields=("quantity_on_hand", "updated_at"))
        StockMovement.objects.create(
            batch=batch,
            kind=StockMovement.Kind.SALE,
            quantity_delta=-quantity,
            quantity_before=before,
            quantity_after=before - quantity,
            reference_type="pharmacy_sale",
            reference_id=str(sale.pk),
            request_key=request_key,
            actor=actor,
        )
        AuditEvent.objects.create(
            actor=actor,
            action="pharmacy.sale_created",
            target_type="pharmacysale",
            target_id=str(sale.pk),
            details={"invoice_id": invoice.pk, "line_id": line.pk},
        )
    messages.success(request, f"Pharmacy sale {sale.number} recorded.")
    return redirect("pharmacy_sale_detail", pk=sale.pk)


@permission_required("core.view_pharmacysale", raise_exception=True)
def pharmacy_sale_detail(request, pk):
    if not _has_role(request.user, "Pharmacy"):
        raise PermissionDenied
    sale = get_object_or_404(
        PharmacySale.objects.select_related("invoice").prefetch_related(
            "lines__batch__medicine"
        ),
        pk=pk,
    )
    for line in sale.lines.all():
        returned = ReturnLine.objects.filter(
            sale_line=line,
            pharmacy_return__status__in=[
                PharmacyReturn.Status.PENDING,
                PharmacyReturn.Status.APPROVED,
            ],
        ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.000")
        line.returnable_quantity = line.quantity - returned
        line.request_key = uuid.uuid4()
    return render(
        request,
        "core/pharmacy/sale_detail.html",
        {"sale": sale, "lines": sale.lines.all()},
    )


@permission_required("core.add_pharmacyreturn", raise_exception=True)
def pharmacy_return_create(request):
    if not _has_role(request.user, "Pharmacy"):
        raise PermissionDenied
    if request.method != "POST":
        return HttpResponseBadRequest("Returns require POST.")
    request_key = _request_key(request)
    if request_key is None:
        return HttpResponseBadRequest("A valid request key is required.")
    existing = PharmacyReturn.objects.filter(request_key=request_key).first()
    if existing:
        line = existing.lines.first()
        if line and line.sale_line_id:
            return redirect("pharmacy_sale_detail", pk=line.sale_line.sale_id)
        return redirect("pharmacy_prescription_list")
    reason = request.POST.get("reason", "").strip()
    if not reason:
        return HttpResponseBadRequest("A return reason is required.")
    try:
        quantity = Decimal(request.POST.get("quantity", "0"))
    except InvalidOperation:
        return HttpResponseBadRequest("Return quantity must be a valid number.")
    if not quantity.is_finite() or quantity <= 0:
        return HttpResponseBadRequest("Return quantity must be positive.")
    sale_line_id = request.POST.get("sale_line", "").strip()
    dispensing_line_id = request.POST.get("dispensing_line", "").strip()
    if bool(sale_line_id) == bool(dispensing_line_id):
        return HttpResponseBadRequest(
            "Select exactly one originating transaction line."
        )

    with transaction.atomic():
        if sale_line_id:
            source = get_object_or_404(
                PharmacySaleLine.objects.select_for_update().select_related("sale"),
                pk=sale_line_id,
            )
            source_field = "sale_line"
            if source.sale.status != PharmacySale.Status.ISSUED:
                return HttpResponseBadRequest("Only issued sales can be returned.")
            patient = source.sale.patient
            unit_price = source.unit_price
            source_quantity = source.quantity
            redirect_url = ("pharmacy_sale_detail", source.sale_id)
        else:
            source = get_object_or_404(
                DispensingLine.objects.select_for_update().select_related(
                    "dispensing__prescription"
                ),
                pk=dispensing_line_id,
            )
            source_field = "dispensing_line"
            if source.dispensing.status != Dispensing.Status.COMPLETED:
                return HttpResponseBadRequest(
                    "Only completed dispensing can be returned."
                )
            patient = source.dispensing.patient
            unit_price = source.unit_price
            source_quantity = source.quantity
            redirect_url = ("pharmacy_prescription_list", None)
        returned = ReturnLine.objects.filter(
            **{source_field: source},
            pharmacy_return__status__in=[
                PharmacyReturn.Status.PENDING,
                PharmacyReturn.Status.APPROVED,
            ],
        ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.000")
        if returned + quantity > source_quantity:
            return HttpResponseBadRequest(
                "Return exceeds the unreturned transaction quantity."
            )
        actor = StaffProfile.objects.get(user=request.user)
        pharmacy_return = PharmacyReturn.objects.create(
            number=next_number("PHARMACY_RETURN"),
            patient=patient,
            reason=reason,
            status=PharmacyReturn.Status.PENDING,
            created_by=actor,
            request_key=request_key,
        )
        line = ReturnLine.objects.create(
            pharmacy_return=pharmacy_return,
            quantity=quantity,
            refund_amount=(unit_price * quantity).quantize(Decimal("0.01")),
            **{source_field: source},
        )
        AuditEvent.objects.create(
            actor=actor,
            action="pharmacy.return_requested",
            target_type="pharmacyreturn",
            target_id=str(pharmacy_return.pk),
            details={
                "source_type": source_field,
                "source_id": source.pk,
                "line_id": line.pk,
                "quantity": str(quantity),
                "reason": reason,
            },
        )
    messages.success(request, f"Return request {pharmacy_return.number} submitted.")
    return redirect(
        redirect_url[0], **({"pk": redirect_url[1]} if redirect_url[1] else {})
    )


@permission_required("core.adjust_stock", raise_exception=True)
def stock_adjustment(request, pk):
    if not _has_role(request.user, "Pharmacy"):
        raise PermissionDenied
    if request.method != "POST":
        return HttpResponseBadRequest("Stock adjustments require POST.")
    request_key = _request_key(request)
    if request_key is None:
        return HttpResponseBadRequest("A valid request key is required.")
    reason = request.POST.get("reason", "").strip()
    if not reason:
        return HttpResponseBadRequest("A reason is required.")
    try:
        delta = Decimal(request.POST.get("quantity_delta", "0"))
    except InvalidOperation:
        return HttpResponseBadRequest("Stock adjustment must be a valid number.")
    if not delta.is_finite() or delta == 0:
        return HttpResponseBadRequest("Stock adjustment must be nonzero.")
    if StockMovement.objects.filter(request_key=request_key).exists():
        return redirect("pharmacy_prescription_list")

    with transaction.atomic():
        batch = get_object_or_404(MedicineBatch.objects.select_for_update(), pk=pk)
        if StockMovement.objects.filter(request_key=request_key).exists():
            return redirect("pharmacy_prescription_list")
        before = batch.quantity_on_hand
        after = before + delta
        if after < 0:
            return HttpResponseBadRequest("Adjustment cannot make stock negative.")
        batch.quantity_on_hand = after
        batch.save(update_fields=("quantity_on_hand", "updated_at"))
        audit = AuditEvent.objects.create(
            actor=StaffProfile.objects.get(user=request.user),
            action="stock.adjusted",
            target_type="medicinebatch",
            target_id=str(batch.pk),
            details={"reason": reason, "quantity_delta": str(delta)},
        )
        StockMovement.objects.create(
            batch=batch,
            kind=StockMovement.Kind.ADJUSTMENT,
            quantity_delta=delta,
            quantity_before=before,
            quantity_after=after,
            reference_type="audit_event",
            reference_id=str(audit.pk),
            request_key=request_key,
            actor=audit.actor,
        )
    messages.success(request, f"Stock adjusted for batch {batch.batch_number}.")
    return redirect("pharmacy_prescription_list")


@permission_required("core.adjust_stock", raise_exception=True)
def batch_quarantine(request, pk):
    if not _has_role(request.user, "Pharmacy"):
        raise PermissionDenied
    if request.method != "POST":
        return HttpResponseBadRequest("Quarantine changes require POST.")
    request_key = _request_key(request)
    if request_key is None:
        return HttpResponseBadRequest("A valid request key is required.")
    reason = request.POST.get("reason", "").strip()
    value = request.POST.get("is_quarantined", "")
    if not reason or value not in {"true", "false"}:
        return HttpResponseBadRequest("A reason and quarantine state are required.")
    if AuditEvent.objects.filter(details__request_key=str(request_key)).exists():
        return redirect("pharmacy_prescription_list")

    with transaction.atomic():
        batch = get_object_or_404(MedicineBatch.objects.select_for_update(), pk=pk)
        batch.is_quarantined = value == "true"
        batch.save(update_fields=("is_quarantined", "updated_at"))
        AuditEvent.objects.create(
            actor=StaffProfile.objects.get(user=request.user),
            action=(
                "stock.quarantined"
                if batch.is_quarantined
                else "stock.quarantine_released"
            ),
            target_type="medicinebatch",
            target_id=str(batch.pk),
            details={"reason": reason, "request_key": str(request_key)},
        )
    state_label = "quarantined" if batch.is_quarantined else "released from quarantine"
    messages.success(request, f"Batch {batch.batch_number} {state_label}.")
    return redirect("pharmacy_prescription_list")


@permission_required("core.add_dispensing", raise_exception=True)
def dispense_prescription(request, prescription_id):
    if not _has_role(request.user, "Pharmacy"):
        raise PermissionDenied
    if request.method != "POST":
        return HttpResponseBadRequest("Dispensing requires POST.")
    request_key = _request_key(request)
    if request_key is None:
        return HttpResponseBadRequest("A valid request key is required.")
    existing = StockMovement.objects.filter(request_key=request_key).first()
    if existing:
        if existing.kind == StockMovement.Kind.DISPENSE:
            return redirect("pharmacy_prescription_list")
        return HttpResponse("Request key already used.", status=409)

    prescription = get_object_or_404(
        Prescription.objects.filter(status=Prescription.Status.ISSUED),
        pk=prescription_id,
    )
    try:
        quantity = Decimal(request.POST.get("quantity", "0"))
    except InvalidOperation:
        return HttpResponseBadRequest("Dispensed quantity must be a valid number.")
    if not quantity.is_finite() or quantity <= 0:
        return HttpResponseBadRequest("Dispensed quantity must be positive.")

    with transaction.atomic():
        item = get_object_or_404(
            PrescriptionItem.objects.select_for_update().filter(
                prescription=prescription
            ),
            pk=request.POST.get("prescription_item"),
        )
        if StockMovement.objects.filter(request_key=request_key).exists():
            return redirect("pharmacy_prescription_list")
        batch = get_object_or_404(
            MedicineBatch.objects.select_for_update().filter(medicine=item.medicine),
            pk=request.POST.get("batch"),
        )
        if batch.expiry_date < timezone.localdate():
            return HttpResponseBadRequest("Expired stock cannot be dispensed.")
        if batch.is_quarantined:
            return HttpResponseBadRequest("Quarantined stock cannot be dispensed.")
        dispensed = DispensingLine.objects.filter(
            prescription_item=item,
            dispensing__status__in=[
                Dispensing.Status.PARTIAL,
                Dispensing.Status.COMPLETED,
            ],
        ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.000")
        if dispensed + quantity > item.quantity:
            return HttpResponseBadRequest(
                "Dispensed quantity exceeds the remaining prescription amount."
            )
        if batch.quantity_on_hand < quantity:
            return HttpResponseBadRequest(
                "Insufficient stock available for this batch."
            )

        actor = StaffProfile.objects.get(user=request.user)
        invoice_total = (batch.sale_price * quantity).quantize(Decimal("0.01"))
        invoice = Invoice.objects.create(
            number=next_number("INVOICE"),
            patient=prescription.patient,
            status=Invoice.Status.ISSUED,
            subtotal=invoice_total,
            tax_total=Decimal("0.00"),
            total=invoice_total,
            issued_at=timezone.now(),
            created_by=actor,
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            description=(
                f"{item.medicine.generic_name} {item.medicine.strength}".strip()
            ),
            quantity=quantity,
            unit_price=batch.sale_price,
            discount_amount=Decimal("0.00"),
            line_total=invoice_total,
        )
        dispensing = Dispensing.objects.create(
            number=next_number("DISPENSING"),
            prescription=prescription,
            invoice=invoice,
            patient=prescription.patient,
            dispensed_by=actor,
            status=Dispensing.Status.COMPLETED,
            dispensed_at=timezone.now(),
        )
        DispensingLine.objects.create(
            dispensing=dispensing,
            prescription_item=item,
            batch=batch,
            quantity=quantity,
            unit_price=batch.sale_price,
        )
        before = batch.quantity_on_hand
        batch.quantity_on_hand = before - quantity
        batch.save(update_fields=("quantity_on_hand", "updated_at"))
        StockMovement.objects.create(
            batch=batch,
            kind=StockMovement.Kind.DISPENSE,
            quantity_delta=-quantity,
            quantity_before=before,
            quantity_after=before - quantity,
            reference_type="dispensing",
            reference_id=str(dispensing.pk),
            request_key=request_key,
            actor=actor,
        )
    messages.success(request, f"Dispensed {quantity} from batch {batch.batch_number}.")
    return redirect("pharmacy_prescription_list")


@permission_required("core.view_prescription", raise_exception=True)
def pharmacy_prescription_list(request):
    if not _has_role(request.user, "Pharmacy"):
        raise PermissionDenied
    query = request.GET.get("q", "").strip()
    prescriptions = Prescription.objects.filter(status=Prescription.Status.ISSUED)
    if query:
        prescriptions = prescriptions.filter(
            Q(number__icontains=query)
            | Q(patient__mrn__icontains=query)
            | Q(patient__full_name__icontains=query)
        )
    prescriptions = list(
        prescriptions.select_related("patient").prefetch_related("items__medicine")
    )
    for prescription in prescriptions:
        for item in prescription.items.all():
            item.request_key = uuid.uuid4()
            dispensed = DispensingLine.objects.filter(
                prescription_item=item,
                dispensing__status__in=[
                    Dispensing.Status.PARTIAL,
                    Dispensing.Status.COMPLETED,
                ],
            ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.000")
            item.remaining_quantity = item.quantity - dispensed
            item.available_batches = MedicineBatch.objects.filter(
                medicine=item.medicine,
                expiry_date__gte=timezone.localdate(),
                is_quarantined=False,
                quantity_on_hand__gt=0,
            ).order_by("expiry_date", "pk")
            item.dispensing_lines = DispensingLine.objects.filter(
                prescription_item=item
            ).select_related("dispensing")
            for line in item.dispensing_lines:
                returned = ReturnLine.objects.filter(
                    dispensing_line=line,
                    pharmacy_return__status__in=[
                        PharmacyReturn.Status.PENDING,
                        PharmacyReturn.Status.APPROVED,
                    ],
                ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.000")
                line.returnable_quantity = line.quantity - returned
                line.return_request_key = uuid.uuid4()

    stock_batches = list(
        MedicineBatch.objects.select_related("medicine").order_by(
            "medicine__generic_name", "expiry_date", "pk"
        )
    )
    for batch in stock_batches:
        batch.adjust_request_key = uuid.uuid4()
        batch.quarantine_request_key = uuid.uuid4()

    return render(
        request,
        "core/clinical/pharmacy_prescriptions.html",
        {
            "prescriptions": prescriptions,
            "stock_batches": stock_batches,
            "otc_batches": MedicineBatch.objects.filter(
                medicine__is_active=True,
                medicine__is_otc=True,
                expiry_date__gte=timezone.localdate(),
                is_quarantined=False,
                quantity_on_hand__gt=0,
            )
            .select_related("medicine")
            .order_by("expiry_date", "pk"),
            "sale_request_key": uuid.uuid4(),
            "query": query,
        },
    )


# ==============================================================================
# INPATIENT HOSPITALIZATION (IPD) MODULE
# ==============================================================================


@permission_required("core.view_admission", raise_exception=True)
def admission_list(request):
    if not (
        _has_role(request.user, "Reception")
        or _has_role(request.user, "Doctor")
        or _has_role(request.user, "Administrator")
    ):
        raise PermissionDenied

    admissions = (
        Admission.objects.select_related(
            "patient", "bed__ward", "admitting_doctor__user"
        )
        .prefetch_related("deposits")
        .order_by("-admitted_at")
    )
    query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()

    if status_filter:
        admissions = admissions.filter(status=status_filter)
    if query:
        admissions = admissions.filter(
            Q(admission_number__icontains=query)
            | Q(patient__mrn__icontains=query)
            | Q(patient__full_name__icontains=query)
            | Q(bed__bed_number__icontains=query)
            | Q(bed__ward__name__icontains=query)
        )

    wards = Ward.objects.filter(is_active=True).prefetch_related("beds")
    total_beds = Bed.objects.count()
    occupied_beds = Bed.objects.filter(status=Bed.Status.OCCUPIED).count()
    available_beds = Bed.objects.filter(status=Bed.Status.AVAILABLE).count()

    return render(
        request,
        "core/ipd/admission_list.html",
        {
            "admissions": admissions,
            "wards": wards,
            "total_beds": total_beds,
            "occupied_beds": occupied_beds,
            "available_beds": available_beds,
            "query": query,
            "status_filter": status_filter,
            "can_admit": _has_role(request.user, "Reception")
            or _has_role(request.user, "Administrator"),
        },
    )


@permission_required("core.add_admission", raise_exception=True)
def admission_create(request):
    if not (
        _has_role(request.user, "Reception") or _has_role(request.user, "Administrator")
    ):
        raise PermissionDenied

    initial = {}
    patient_id = request.GET.get("patient")
    if patient_id:
        initial["patient"] = patient_id

    form = AdmissionForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            admission = form.save(commit=False)
            admission.admission_number = next_number("ADMISSION")
            admission.admitted_by = StaffProfile.objects.filter(
                user=request.user
            ).first()
            admission.save()

            # Mark bed as occupied
            bed = admission.bed
            bed.status = Bed.Status.OCCUPIED
            bed.save(update_fields=["status"])

            _audit_patient_change(
                request,
                admission.patient,
                "ipd.patient_admitted",
                [
                    f"adm:{admission.admission_number}",
                    f"ward:{bed.ward.name}",
                    f"bed:{bed.bed_number}",
                ],
            )
        messages.success(
            request,
            f"Patient {admission.patient.full_name} admitted to {bed.ward.name} (Bed {bed.bed_number}) successfully.",
        )
        return redirect("admission_detail", pk=admission.pk)

    return render(
        request,
        "core/ipd/admission_form.html",
        {"form": form, "creating": True},
    )


@permission_required("core.view_admission", raise_exception=True)
def admission_detail(request, pk):
    if not (
        _has_role(request.user, "Reception")
        or _has_role(request.user, "Doctor")
        or _has_role(request.user, "Administrator")
    ):
        raise PermissionDenied

    admission = get_object_or_404(
        Admission.objects.select_related(
            "patient", "bed__ward", "admitting_doctor__user", "admitted_by__user"
        ).prefetch_related("deposits__payment_method", "deposits__received_by__user"),
        pk=pk,
    )
    can_manage_finance = _has_role(request.user, "Reception") or _has_role(
        request.user, "Administrator"
    )
    can_discharge = (
        _has_role(request.user, "Doctor")
        or _has_role(request.user, "Administrator")
        or _has_role(request.user, "Reception")
    )

    deposit_form = InpatientDepositForm() if can_manage_finance else None
    discharge_form = (
        DischargeForm(instance=admission)
        if (can_discharge and admission.status == Admission.Status.ADMITTED)
        else None
    )

    return render(
        request,
        "core/ipd/admission_detail.html",
        {
            "admission": admission,
            "deposits": admission.deposits.all(),
            "deposit_form": deposit_form,
            "discharge_form": discharge_form,
            "can_manage_finance": can_manage_finance,
            "can_discharge": can_discharge,
        },
    )


@permission_required("core.add_inpatientdeposit", raise_exception=True)
def inpatient_deposit_create(request, admission_id):
    if not (
        _has_role(request.user, "Reception") or _has_role(request.user, "Administrator")
    ):
        raise PermissionDenied

    admission = get_object_or_404(Admission, pk=admission_id)
    if request.method == "POST":
        form = InpatientDepositForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                deposit = form.save(commit=False)
                deposit.admission = admission
                deposit.receipt_number = next_number("DEPOSIT")
                deposit.received_by = StaffProfile.objects.filter(
                    user=request.user
                ).first()
                deposit.save()

                _audit_patient_change(
                    request,
                    admission.patient,
                    "ipd.deposit_received",
                    [
                        f"receipt:{deposit.receipt_number}",
                        f"amount:{deposit.amount}",
                        f"method:{deposit.payment_method.name}",
                        f"ref:{deposit.transaction_reference}",
                    ],
                )
            messages.success(
                request,
                f"Advance deposit of ₹{deposit.amount} recorded successfully (Receipt #{deposit.receipt_number}).",
            )
        else:
            messages.error(request, "Failed to record deposit. Please verify input fields.")

    return redirect("admission_detail", pk=admission.pk)


@permission_required("core.change_admission", raise_exception=True)
def admission_discharge(request, pk):
    if not (
        _has_role(request.user, "Doctor")
        or _has_role(request.user, "Administrator")
        or _has_role(request.user, "Reception")
    ):
        raise PermissionDenied

    admission = get_object_or_404(
        Admission.objects.filter(status=Admission.Status.ADMITTED), pk=pk
    )

    if request.method == "POST":
        form = DischargeForm(request.POST, instance=admission)
        if form.is_valid():
            with transaction.atomic():
                adm = form.save(commit=False)
                adm.discharged_at = timezone.now()
                adm.save()

                # Free the bed
                bed = adm.bed
                bed.status = Bed.Status.AVAILABLE
                bed.save(update_fields=["status"])

                _audit_patient_change(
                    request,
                    adm.patient,
                    "ipd.patient_discharged",
                    [
                        f"adm:{adm.admission_number}",
                        f"condition:{adm.discharge_condition}",
                        f"status:{adm.status}",
                    ],
                )
            messages.success(
                request,
                f"Patient {adm.patient.full_name} has been discharged. Bed {bed.bed_number} is now marked Available.",
            )
        else:
            messages.error(request, "Failed to process discharge. Please check all fields.")

    return redirect("admission_detail", pk=admission.pk)

