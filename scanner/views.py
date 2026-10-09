import pandas as pd
import json
from datetime import date
from django.utils import timezone
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models.functions import Length
from .models import User, AttendanceRecord

# --- Role Checks ---
def is_admin_or_super(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name='Admin').exists())

def is_viewer_or_higher(user):
    return user.is_authenticated

# --- Views ---

@user_passes_test(is_admin_or_super, login_url='/accounts/login/')
def index(request):
    """Scanner Page - Restricted to Admin/SuperAdmin"""
    return render(request, 'index.html')

@login_required
def dashboard(request):
    """Dashboard Page - Open to all logged-in users"""
    from django.db.models import Count, Q
    total_users = User.objects.count()
    attended = AttendanceRecord.objects.filter(scan_time__date=date.today()).values('user').distinct().count()
    not_attended = total_users - attended
    percent = round((attended / total_users * 100), 1) if total_users > 0 else 0
    recent_scans = AttendanceRecord.objects.filter(
        scan_time__date=date.today()
    ).select_related('user').order_by('-scan_time')[:20]

    category_stats_qs = User.objects.values('category').annotate(
        total=Count('user_id'),
        attended=Count('attendancerecord', filter=Q(attendancerecord__scan_time__date=date.today()))
    ).order_by('category')
    
    category_stats = []
    for stat in category_stats_qs:
        total = stat['total']
        attended_cat = stat['attended']
        not_attended_cat = total - attended_cat
        percent_cat = round((attended_cat / total * 100), 1) if total > 0 else 0
        category_stats.append({
            'category': stat['category'],
            'total': total,
            'attended': attended_cat,
            'not_attended': not_attended_cat,
            'percent': percent_cat,
        })
        
    # Sort so that 'PB' (Presbyters) comes first
    category_stats.sort(key=lambda x: 0 if x['category'] and x['category'].upper() == 'PB' else 1)

    context = {
        'total_users': total_users,
        'attended': attended,
        'not_attended': not_attended,
        'percent': percent,
        'recent_scans': recent_scans,
        'category_stats': category_stats,
    }
    return render(request, 'dashboard.html', context)

@user_passes_test(is_admin_or_super, login_url='/accounts/login/')
def delegates_list(request):
    """Filterable list of all delegates - Admin/SuperAdmin only"""
    users = User.objects.annotate(slno_len=Length('slno')).order_by('slno_len', 'slno')
    
    church = request.GET.get('church')
    constituency = request.GET.get('constituency')
    category = request.GET.get('category')
    status = request.GET.get('status')
    search_query = request.GET.get('search', '').strip()
    
    from django.db.models import Q
    if search_query:
        users = users.filter(
            Q(name__icontains=search_query) |
            Q(seat_no__icontains=search_query) |
            Q(slno__icontains=search_query) |
            Q(user_id__icontains=search_query)
        )
    
    if church:
        users = users.filter(church__iexact=church)
    if constituency:
        users = users.filter(constituency__iexact=constituency)
    if category:
        users = users.filter(category__iexact=category)
        
    today = date.today()
    
    # Annotate users with attendance status
    users_with_status = []
    for u in users:
        attended = AttendanceRecord.objects.filter(user=u, scan_time__date=today).exists()
        if status == 'attended' and not attended:
            continue
        if status == 'not_attended' and attended:
            continue
        u.has_attended = attended
        users_with_status.append(u)
        
    churches = User.objects.values_list('church', flat=True).distinct().exclude(church__isnull=True).exclude(church='')
    constituencies = User.objects.values_list('constituency', flat=True).distinct().exclude(constituency__isnull=True).exclude(constituency='')
    categories = User.objects.values_list('category', flat=True).distinct().exclude(category__isnull=True).exclude(category='')
    
    context = {
        'users': users_with_status,
        'churches': churches,
        'constituencies': constituencies,
        'categories': categories,
        'selected_church': church,
        'selected_constituency': constituency,
        'selected_category': category,
        'selected_status': status,
        'search_query': search_query,
    }
    return render(request, 'delegates.html', context)


@user_passes_test(lambda u: u.is_superuser, login_url='/accounts/login/')
def admin_page(request):
    """Excel Upload Page - Restricted to SuperAdmin"""
    users = User.objects.annotate(slno_len=Length('slno')).order_by('slno_len', 'slno')
    return render(request, 'admin.html', {'users': users})

from django.core.paginator import Paginator
import qrcode
import io
import base64

@user_passes_test(lambda u: u.is_superuser, login_url='/accounts/login/')
def users_list(request):
    """Barcodes Print Page - Restricted to SuperAdmin"""
    users_qs = User.objects.annotate(slno_len=Length('slno')).order_by('slno_len', 'slno')
    paginator = Paginator(users_qs, 60) # 60 barcodes per page (20 rows of 3)
    
    page_number = request.GET.get('page')
    users = paginator.get_page(page_number)
    
    for u in users:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=4,
            border=1,
        )
        qr_data = str(u.seat_no).strip() if (u.seat_no and str(u.seat_no).strip()) else str(u.user_id)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        u.qr_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    return render(request, 'users.html', {'users': users})

@csrf_exempt
def upload_users(request):
    # API endpoint protected manually
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
        
    if request.method == 'POST':
        if 'file' not in request.FILES:
            return JsonResponse({'error': 'No file part'}, status=400)
        
        file = request.FILES['file']
        if file.name == '':
            return JsonResponse({'error': 'No selected file'}, status=400)
            
        if file and (file.name.endswith('.xlsx') or file.name.endswith('.xls') or file.name.endswith('.csv')):
            try:
                if file.name.endswith('.csv'):
                    df = pd.read_csv(file)
                else:
                    df = pd.read_excel(file)
                
                df.columns = df.columns.str.strip().str.lower()
                
                required_cols = ['name', 'seat no']
                for col in required_cols:
                    if col not in df.columns:
                        return JsonResponse({'error': f'File must contain "{col}" column'}, status=400)
                
                if 'id' in df.columns:
                    df['id'] = df['id'].astype(str).str.replace(r'\.0$', '', regex=True)
                    
                success_count = 0
                for index, row in df.iterrows():
                    name = str(row['name']).strip()
                    seat_no_val = str(row['seat no']).strip()
                    
                    if 'id' in df.columns and str(row['id']).strip() and str(row['id']).strip() != 'nan':
                        user_id = str(row['id']).strip()
                    else:
                        user_id = seat_no_val
                    
                    def get_val(col_name):
                        val = str(row.get(col_name, '')).strip()
                        return None if val == 'nan' or val == '' else val

                    slno = get_val('slno')
                    image_name = get_val('image name')
                    church = get_val('church')
                    seat_no = get_val('seat no')
                    constituency = get_val('constituency')
                    category = get_val('category')
                    
                    user, created = User.objects.update_or_create(
                        user_id=user_id,
                        defaults={
                            'name': name,
                            'slno': slno,
                            'image_name': image_name,
                            'church': church,
                            'seat_no': seat_no,
                            'constituency': constituency,
                            'category': category
                        }
                    )
                    success_count += 1
                
                return JsonResponse({'message': f'Successfully imported {success_count} users!'}, status=200)
                
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=500)
        else:
            return JsonResponse({'error': 'Invalid file format. Please upload an Excel or CSV file.'}, status=400)
    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
def scan_barcode(request):
    # API endpoint protected manually
    # if not is_admin_or_super(request.user):
    #     return JsonResponse({'error': 'Unauthorized: Only Admins can scan'}, status=403)
        
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
            
        if not data or 'user_id' not in data:
            return JsonResponse({'error': 'Missing user_id'}, status=400)
            
        scanned_val = data['user_id'].strip()
        
        try:
            user = User.objects.get(seat_no=scanned_val)
        except User.DoesNotExist:
            try:
                user = User.objects.get(user_id=scanned_val)
            except User.DoesNotExist:
                return JsonResponse({'error': 'Delegate Not Found'}, status=404)
        except User.MultipleObjectsReturned:
            user = User.objects.filter(seat_no=scanned_val).first()
            
        today = timezone.localdate()
        
        existing_scan = AttendanceRecord.objects.filter(
            user=user,
            scan_time__date=today
        ).exists()
        
        user_data = {
            'user_id': user.user_id,
            'name': user.name,
            'image_name': user.image_name,
            'church': user.church,
            'seat_no': user.seat_no,
            'constituency': user.constituency,
            'category': user.category,
            'slno': user.slno,
        }

        if existing_scan:
            return JsonResponse({'error': 'Already Marked Present Today', 'user': user_data}, status=409)
            
        AttendanceRecord.objects.create(user=user)
        
        return JsonResponse({
            'message': 'Success',
            'user': user_data
        }, status=200)
    return JsonResponse({'error': 'Invalid request'}, status=400)


# --- Frontend Admin Features ---
from django.shortcuts import get_object_or_404
import csv
from django.http import HttpResponse

@user_passes_test(lambda u: u.is_superuser, login_url='/accounts/login/')
def edit_delegate(request, user_id):
    user = get_object_or_404(User, user_id=user_id)
    if request.method == 'POST':
        user.name = request.POST.get('name')
        user.slno = request.POST.get('slno')
        user.church = request.POST.get('church')
        user.category = request.POST.get('category')
        user.seat_no = request.POST.get('seat_no')
        user.constituency = request.POST.get('constituency')
        user.save()
        return redirect('delegates_list')
    return render(request, 'edit_delegate.html', {'user': user})

@user_passes_test(lambda u: u.is_superuser, login_url='/accounts/login/')
def delete_delegate(request, user_id):
    if request.method == 'POST':
        user = get_object_or_404(User, user_id=user_id)
        user.delete()
    return redirect('delegates_list')

@user_passes_test(lambda u: u.is_superuser, login_url='/accounts/login/')
def bulk_delete_delegates(request):
    if request.method == 'POST':
        user_ids = request.POST.getlist('selected_users')
        if user_ids:
            User.objects.filter(user_id__in=user_ids).delete()
    return redirect('delegates_list')

@user_passes_test(lambda u: u.is_superuser, login_url='/accounts/login/')
def export_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="delegates_report.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['SL No', 'Name', 'Church', 'Seat No', 'Constituency', 'Category', 'Attendance Status'])
    
    users = User.objects.annotate(slno_len=Length('slno')).order_by('slno_len', 'slno')
    today = date.today()
    for u in users:
        attended = AttendanceRecord.objects.filter(user=u, scan_time__date=today).exists()
        status = 'Attended' if attended else 'Not Attended'
        
        cat_display = u.category
        if cat_display:
            if cat_display.upper() == 'PB': cat_display = 'Presbyters'
            elif cat_display.upper() == 'LP': cat_display = 'Laypersons'
            
        writer.writerow([u.slno, u.name, u.church, u.seat_no, u.constituency, cat_display, status])
        
    return response

@user_passes_test(lambda u: u.is_superuser, login_url='/accounts/login/')
def generate_single_qr(request, user_id):
    user = get_object_or_404(User, user_id=user_id)
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=5,
        border=1,
    )
    qr_data = str(user.seat_no).strip() if (user.seat_no and str(user.seat_no).strip()) else str(user.user_id)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    return render(request, 'single_qr.html', {'user': user, 'qr_base64': qr_base64})


# ── Attendance Report ────────────────────────────────────────────────────────
@user_passes_test(is_viewer_or_higher, login_url='/accounts/login/')
def attendance_report(request):
    selected_date   = request.GET.get('date', str(timezone.localdate()))
    selected_church = request.GET.get('church', '')
    selected_category = request.GET.get('category', '')
    selected_status = request.GET.get('status', '')
    search_query    = request.GET.get('search', '').strip()
    export          = request.GET.get('export', '')

    try:
        from datetime import datetime
        report_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        report_date = timezone.localdate()
        selected_date = str(report_date)

    users_qs = User.objects.annotate(slno_len=Length('slno')).order_by('slno_len', 'slno')
    
    from django.db.models import Q
    if search_query:
        users_qs = users_qs.filter(
            Q(name__icontains=search_query) |
            Q(seat_no__icontains=search_query) |
            Q(slno__icontains=search_query) |
            Q(user_id__icontains=search_query)
        )
        
    if selected_church:
        users_qs = users_qs.filter(church__iexact=selected_church)
    if selected_category:
        users_qs = users_qs.filter(category__iexact=selected_category)

    records = []
    for u in users_qs:
        record = AttendanceRecord.objects.filter(user=u, scan_time__date=report_date).order_by('scan_time').first()
        attended = record is not None
        if selected_status == 'attended' and not attended:
            continue
        if selected_status == 'absent' and attended:
            continue
        records.append({
            'user': u,
            'attended': attended,
            'scan_time': record.scan_time if record else None,
        })

    if export == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="attendance_{selected_date}.csv"'
        writer = csv.writer(response)
        writer.writerow(['SL No', 'Name', 'Church', 'Constituency', 'Seat No', 'Category', 'Status', 'Scan Time'])
        for row in records:
            cat_display = row['user'].category
            if cat_display:
                if cat_display.upper() == 'PB': cat_display = 'Presbyters'
                elif cat_display.upper() == 'LP': cat_display = 'Laypersons'
                
            writer.writerow([
                row['user'].slno, row['user'].name,
                row['user'].church, row['user'].constituency, row['user'].seat_no, cat_display,
                'Present' if row['attended'] else 'Absent',
                row['scan_time'].strftime('%d %b %Y %H:%M') if row['scan_time'] else ''
            ])
        return response
        
    elif export == 'pdf':
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="attendance_{selected_date}.pdf"'
        
        doc = SimpleDocTemplate(response, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        elements = []
        
        styles = getSampleStyleSheet()
        elements.append(Paragraph(f"Attendance Report - {selected_date}", styles['Title']))
        if selected_church:
            elements.append(Paragraph(f"Church: {selected_church}", styles['Normal']))
        if selected_category:
            elements.append(Paragraph(f"Category: {selected_category}", styles['Normal']))
        if selected_status:
            elements.append(Paragraph(f"Status: {selected_status.title()}", styles['Normal']))
        elements.append(Spacer(1, 20))
        
        data = [['SL No', 'Name', 'Church', 'Constituency', 'Seat No', 'Category', 'Status', 'Scan Time']]
        for row in records:
            cat_display = str(row['user'].category or '-')
            if cat_display.upper() == 'PB': cat_display = 'Presbyters'
            elif cat_display.upper() == 'LP': cat_display = 'Laypersons'
            
            data.append([
                str(row['user'].slno or '-'), 
                str(row['user'].name or '-'),
                str(row['user'].church or '-'),
                str(row['user'].constituency or '-'),
                str(row['user'].seat_no or '-'),
                cat_display,
                'Present' if row['attended'] else 'Absent',
                row['scan_time'].strftime('%H:%M') if row['scan_time'] else '-'
            ])
            
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
        ]))
        
        elements.append(table)
        doc.build(elements)
        return response

    churches = User.objects.values_list('church', flat=True).distinct().exclude(church__isnull=True).exclude(church='')
    categories = User.objects.values_list('category', flat=True).distinct().exclude(category__isnull=True).exclude(category='')
    return render(request, 'attendance.html', {
        'records': records,
        'churches': churches,
        'categories': categories,
        'selected_date': selected_date,
        'selected_church': selected_church,
        'selected_category': selected_category,
        'selected_status': selected_status,
        'search_query': search_query,
    })


@user_passes_test(is_admin_or_super, login_url='/accounts/login/')
def mark_attendance(request, user_id):
    """Manually mark a delegate as present."""
    if request.method == 'POST':
        user = get_object_or_404(User, user_id=user_id)
        if not AttendanceRecord.objects.filter(user=user, scan_time__date=timezone.localdate()).exists():
            AttendanceRecord.objects.create(user=user)
        # Redirect back to report
    return redirect(request.META.get('HTTP_REFERER', '/attendance/'))


@user_passes_test(is_admin_or_super, login_url='/accounts/login/')
def reset_attendance(request, user_id):
    """Remove today's attendance for a delegate."""
    if request.method == 'POST':
        user = get_object_or_404(User, user_id=user_id)
        date_str = request.POST.get('date', str(timezone.localdate()))
        try:
            from datetime import datetime
            reset_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            reset_date = timezone.localdate()
        AttendanceRecord.objects.filter(user=user, scan_time__date=reset_date).delete()
    return redirect(request.META.get('HTTP_REFERER', '/attendance/'))

from django.contrib.auth.models import User as AuthUser, Group
from django.contrib.auth.hashers import make_password

@user_passes_test(lambda u: u.is_superuser, login_url='/accounts/login/')
def system_users(request):
    users = AuthUser.objects.all().order_by('id')
    return render(request, 'system_users.html', {'users': users})

@user_passes_test(lambda u: u.is_superuser, login_url='/accounts/login/')
def add_system_user(request):
    if request.method == 'POST':
        username = request.POST.get('username').strip()
        password = request.POST.get('password')
        role = request.POST.get('role')
        
        if username and password and not AuthUser.objects.filter(username=username).exists():
            is_super = (role == 'superuser')
            user = AuthUser.objects.create(
                username=username,
                password=make_password(password),
                is_superuser=is_super,
                is_staff=is_super
            )
            if role == 'admin':
                group, _ = Group.objects.get_or_create(name='Admin')
                user.groups.add(group)
            elif role == 'viewer':
                group, _ = Group.objects.get_or_create(name='Viewer')
                user.groups.add(group)
            
    return redirect('system_users')

@user_passes_test(lambda u: u.is_superuser, login_url='/accounts/login/')
def delete_system_user(request, user_id):
    if request.method == 'POST':
        user = get_object_or_404(AuthUser, id=user_id)
        if not user.is_superuser or AuthUser.objects.filter(is_superuser=True).count() > 1:
            user.delete()
    return redirect('system_users')
