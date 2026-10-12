import os
import shutil
import zipfile
import tempfile
from pathlib import Path
from django.conf import settings
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
        
    def get_cat_sort(cat_val):
        c = (cat_val or '').upper()
        if c == 'DO': return 0
        if c == 'PB': return 1
        if c == 'LP': return 2
        if c == 'NOM': return 3
        return 4

    # Sort so that 'DO' (Diocesan Officers) comes first, then 'PB' (Presbyters), then 'LP' (Laypersons), then 'Nom' (Nominee)
    category_stats.sort(key=lambda x: get_cat_sort(x['category']))

    context = {
        'total_users': total_users,
        'attended': attended,
        'not_attended': not_attended,
        'percent': percent,
        'recent_scans': recent_scans,
        'category_stats': category_stats,
    }
    return render(request, 'dashboard.html', context)

@login_required
def api_dashboard_data(request):
    from django.db.models import Count, Q
    from django.utils.timezone import localtime
    total_users = User.objects.count()
    attended = AttendanceRecord.objects.filter(scan_time__date=date.today()).values('user').distinct().count()
    not_attended = total_users - attended
    percent = round((attended / total_users * 100), 1) if total_users > 0 else 0
    
    recent_qs = AttendanceRecord.objects.filter(scan_time__date=date.today()).select_related('user').order_by('-scan_time')[:10]
    recent_scans = []
    for r in recent_qs:
        cat_disp = r.user.category
        if cat_disp:
            if cat_disp.upper() == 'PB': cat_disp = 'Presbyters'
            elif cat_disp.upper() == 'LP': cat_disp = 'Laypersons'
            elif cat_disp.upper() == 'DO': cat_disp = 'Diocesan Officers'
            elif cat_disp.upper() == 'NOM': cat_disp = 'Nominee'
        
        recent_scans.append({
            'user_id': r.user.user_id,
            'name': r.user.name,
            'church': r.user.church or '-',
            'constituency': r.user.constituency or '-',
            'category': cat_disp or '-',
            'time': localtime(r.scan_time).strftime("%I:%M %p")
        })

    category_stats_qs = User.objects.values('category').annotate(
        total=Count('user_id'),
        attended=Count('attendancerecord', filter=Q(attendancerecord__scan_time__date=date.today()))
    ).order_by('category')
    
    category_stats = []
    for stat in category_stats_qs:
        total = stat['total']
        attended_cat = stat['attended']
        percent_cat = round((attended_cat / total * 100), 1) if total > 0 else 0
        cat_disp = stat['category']
        if cat_disp:
            if cat_disp.upper() == 'PB': cat_disp = 'Presbyters'
            elif cat_disp.upper() == 'LP': cat_disp = 'Laypersons'
            elif cat_disp.upper() == 'DO': cat_disp = 'Diocesan Officers'
            elif cat_disp.upper() == 'NOM': cat_disp = 'Nominee'
        category_stats.append({
            'category_raw': stat['category'],
            'category': cat_disp or 'Uncategorized',
            'total': total,
            'attended': attended_cat,
            'not_attended': total - attended_cat,
            'percent': percent_cat,
        })
    category_stats.sort(key=lambda x: 0 if x['category_raw'] and x['category_raw'].upper() == 'DO' else (1 if x['category_raw'] and x['category_raw'].upper() == 'PB' else (2 if x['category_raw'] and x['category_raw'].upper() == 'LP' else (3 if x['category_raw'] and x['category_raw'].upper() == 'NOM' else 4))))

    # Hourly Check-ins
    all_scans = AttendanceRecord.objects.filter(scan_time__date=date.today())
    hourly_counts = {}
    for scan in all_scans:
        hour_str = localtime(scan.scan_time).strftime("%I %p")
        hourly_counts[hour_str] = hourly_counts.get(hour_str, 0) + 1
        
    return JsonResponse({
        'total_users': total_users,
        'attended': attended,
        'not_attended': not_attended,
        'percent': percent,
        'recent_scans': recent_scans,
        'category_stats': category_stats,
        'hourly_keys': list(hourly_counts.keys()),
        'hourly_values': list(hourly_counts.values())
    })


@user_passes_test(is_admin_or_super, login_url='/accounts/login/')
def delegates_list(request):
    """Filterable list of all delegates - Admin/SuperAdmin only"""
    users = User.objects.annotate(slno_len=Length('slno')).order_by('slno_len', 'slno')
    
    church = request.GET.get('church')
    constituency = request.GET.get('constituency')
    category = request.GET.get('category')
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
        
    churches = User.objects.values_list('church', flat=True).distinct().exclude(church__isnull=True).exclude(church='')
    constituencies = User.objects.values_list('constituency', flat=True).distinct().exclude(constituency__isnull=True).exclude(constituency='')
    cats = list(User.objects.values_list('category', flat=True).distinct().exclude(category__isnull=True).exclude(category=''))
    categories = sorted(cats, key=lambda c: 0 if c.upper() == 'DO' else (1 if c.upper() == 'PB' else (2 if c.upper() == 'LP' else (3 if c.upper() == 'NOM' else 4))))
    
    context = {
        'users': users,
        'churches': churches,
        'constituencies': constituencies,
        'categories': categories,
        'selected_church': church,
        'selected_constituency': constituency,
        'selected_category': category,
        'search_query': search_query,
    }
    return render(request, 'delegates.html', context)


@user_passes_test(lambda u: u.is_superuser, login_url='/accounts/login/')
def admin_page(request):
    """Excel & Images Upload Page - Restricted to SuperAdmin"""
    users = User.objects.annotate(slno_len=Length('slno')).order_by('slno_len', 'slno')
    
    images_count = 0
    allowed_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
    static_dirs = getattr(settings, 'STATICFILES_DIRS', [])
    if static_dirs:
        images_dir = Path(static_dirs[0]) / 'images'
        if images_dir.exists():
            images_count = len([f for f in images_dir.iterdir() if f.is_file() and f.suffix.lower() in allowed_exts])
            
    return render(request, 'admin.html', {'users': users, 'images_count': images_count})

from django.core.paginator import Paginator
import qrcode
import io
import base64

@user_passes_test(lambda u: u.is_superuser, login_url='/accounts/login/')
def users_list(request):
    """Barcodes Print Page - Restricted to SuperAdmin"""
    users_qs = User.objects.annotate(slno_len=Length('slno')).order_by('slno_len', 'slno')
    paginator = Paginator(users_qs, 1000) # Print all barcodes on one page (up to 1000)
    
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
def upload_images(request):
    """Upload a folder or zip of images to static/images/ (and delegates/) replacing previous images"""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Unauthorized: Only SuperAdmin can upload images'}, status=403)
        
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
        
    uploaded_files = request.FILES.getlist('images') or request.FILES.getlist('files') or request.FILES.getlist('file')
    if not uploaded_files:
        return JsonResponse({'error': 'No files received. Please select an images folder or zip file.'}, status=400)

    allowed_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
    temp_dir = tempfile.mkdtemp()
    
    try:
        saved_count = 0
        for uploaded_file in uploaded_files:
            file_name = uploaded_file.name.lower()
            if file_name.endswith('.zip'):
                try:
                    with zipfile.ZipFile(uploaded_file, 'r') as zf:
                        for member in zf.namelist():
                            base_name = os.path.basename(member)
                            if not base_name or base_name.startswith('.'):
                                continue
                            ext = os.path.splitext(base_name)[1].lower()
                            if ext in allowed_extensions:
                                target_path = os.path.join(temp_dir, base_name)
                                with zf.open(member) as source, open(target_path, 'wb') as dest:
                                    shutil.copyfileobj(source, dest)
                                saved_count += 1
                except Exception as ze:
                    return JsonResponse({'error': f'Invalid ZIP archive: {str(ze)}'}, status=400)
            else:
                base_name = os.path.basename(uploaded_file.name)
                if not base_name or base_name.startswith('.'):
                    continue
                ext = os.path.splitext(base_name)[1].lower()
                if ext in allowed_extensions:
                    target_path = os.path.join(temp_dir, base_name)
                    with open(target_path, 'wb') as dest:
                        for chunk in uploaded_file.chunks():
                            dest.write(chunk)
                    saved_count += 1
                    
        temp_images = [f for f in os.listdir(temp_dir) if os.path.isfile(os.path.join(temp_dir, f))]
        if not temp_images:
            return JsonResponse({'error': 'No valid image files (.jpg, .jpeg, .png, .webp) found in the upload.'}, status=400)
            
        # Target directories: only static/images/
        target_dirs = []
        static_dirs = getattr(settings, 'STATICFILES_DIRS', [])
        if static_dirs:
            primary_static = Path(static_dirs[0])
            target_dirs.append(primary_static / 'images')
            
        proj_root_static = Path(__file__).resolve().parent.parent / 'static'
        if proj_root_static.exists():
            target_dirs.append(proj_root_static / 'images')

        unique_dirs = []
        for d in target_dirs:
            try:
                p = d.resolve()
                if p not in unique_dirs:
                    unique_dirs.append(p)
            except Exception:
                pass

        # 1. Clear previous images from target directories
        for d in unique_dirs:
            d.mkdir(parents=True, exist_ok=True)
            # Remove legacy 'delegates' folder if present
            legacy_sub = d / 'delegates'
            if legacy_sub.exists() and legacy_sub.is_dir():
                shutil.rmtree(legacy_sub, ignore_errors=True)
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() in allowed_extensions:
                    try:
                        f.unlink()
                    except Exception:
                        pass

        # 2. Copy the new images into all target directories
        for img_name in temp_images:
            src_file = os.path.join(temp_dir, img_name)
            for d in unique_dirs:
                dst_file = d / img_name
                shutil.copy2(src_file, dst_file)
                
        return JsonResponse({
            'message': f'Successfully uploaded and replaced {len(temp_images)} images in static/images!',
            'count': len(temp_images)
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': f'Upload failed: {str(e)}'}, status=500)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

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
    writer.writerow(['SL No', 'Name', 'Church', 'Seat No', 'Constituency', 'Category'])
    
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
    for u in users:
        if status:
            attended = AttendanceRecord.objects.filter(user=u, scan_time__date=today).exists()
            if status == 'attended' and not attended:
                continue
            if status == 'not_attended' and attended:
                continue
            
        cat_display = u.category
        if cat_display:
            if cat_display.upper() == 'PB': cat_display = 'Presbyters'
            elif cat_display.upper() == 'LP': cat_display = 'Laypersons'
            elif cat_display.upper() == 'DO': cat_display = 'Diocesan Officers'
            elif cat_display.upper() == 'NOM': cat_display = 'Nominee'
            
        writer.writerow([u.slno, u.name, u.church, u.seat_no, u.constituency, cat_display])
        
    return response

@user_passes_test(lambda u: u.is_superuser, login_url='/accounts/login/')
def export_delegates_pdf(request):
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="delegates_list.pdf"'
    
    doc = SimpleDocTemplate(response, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=30, title="Delegates List")
    elements = []
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'MainTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=4,
        textColor=colors.HexColor('#4f46e5'),
        alignment=1
    )
    subtitle_style = ParagraphStyle(
        'SubTitle',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=25,
        textColor=colors.HexColor('#64748b'),
        alignment=1
    )
    
    elements.append(Paragraph("<b>CSI MKD COUNCIL 2026</b>", title_style))
    elements.append(Paragraph(f"Delegates List &nbsp; | &nbsp; Generated: {date.today().strftime('%d %b %Y')}", subtitle_style))
    
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.white
    )
    header_center = ParagraphStyle(
        'HeaderCenter',
        parent=header_style,
        alignment=1
    )

    cell_style = ParagraphStyle(
        'CellNormal',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#1e293b')
    )
    cell_center = ParagraphStyle(
        'CellCenter',
        parent=cell_style,
        alignment=1
    )

    data = [[
        Paragraph('SL No', header_center),
        Paragraph('Name', header_style),
        Paragraph('Church', header_style),
        Paragraph('Seat No', header_center),
        Paragraph('Constituency', header_style),
        Paragraph('Category', header_style)
    ]]
    
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
        
    table_style_commands = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4f46e5')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]
    
    today = date.today()
    row_idx = 1

    for u in users:
        if status:
            attended = AttendanceRecord.objects.filter(user=u, scan_time__date=today).exists()
            if status == 'attended' and not attended:
                continue
            if status == 'not_attended' and attended:
                continue
            
        if row_idx % 2 == 0:
            table_style_commands.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#f8fafc')))
        else:
            table_style_commands.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.white))
            
        cat_display = u.category
        if cat_display:
            if cat_display.upper() == 'PB': cat_display = 'Presbyters'
            elif cat_display.upper() == 'LP': cat_display = 'Laypersons'
            elif cat_display.upper() == 'DO': cat_display = 'Diocesan Officers'
            elif cat_display.upper() == 'NOM': cat_display = 'Nominee'
        
        data.append([
            Paragraph(str(u.slno or '-'), cell_center), 
            Paragraph(str(u.name or '-'), cell_style), 
            Paragraph(str(u.church or '-'), cell_style), 
            Paragraph(str(u.seat_no or '-'), cell_center), 
            Paragraph(str(u.constituency or '-'), cell_style), 
            Paragraph(str(cat_display or '-'), cell_style), 
        ])
        row_idx += 1
        
    table = Table(data, colWidths=[35, 145, 115, 60, 100, 100])
    table.setStyle(TableStyle(table_style_commands))
    
    elements.append(table)
    doc.build(elements)
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


# ── QR Code PDF Export (Server-side) ─────────────────────────────────────────
@user_passes_test(lambda u: u.is_superuser, login_url='/accounts/login/')
def generate_qr_pdf(request):
    """Generate a server-side PDF with all delegates' QR codes using ReportLab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Image as RLImage, Paragraph
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="all_qr_codes.pdf"'

    # A4 = 210mm wide. Margins 8mm each side => usable = 194mm.
    # 5 columns => each column = 194/5 = 38.8mm
    PAGE_MARGIN = 8 * mm
    COLS = 5
    A4_WIDTH = 210 * mm
    usable_width = A4_WIDTH - 2 * PAGE_MARGIN
    cell_w  = usable_width / COLS          # ~38.8mm per column
    qr_size = cell_w - 4 * mm             # QR image slightly smaller than cell

    label_style = ParagraphStyle(
        'qr_label',
        fontSize=6,
        leading=8,
        alignment=TA_CENTER,
        spaceAfter=0,
        spaceBefore=1,
        wordWrap='CJK',
    )

    users_qs = User.objects.annotate(slno_len=Length('slno')).order_by('slno_len', 'slno')

    all_cells = []
    for u in users_qs:
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=6, border=1)
        qr_data = str(u.seat_no).strip() if (u.seat_no and str(u.seat_no).strip()) else str(u.user_id)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        rl_img = RLImage(buf, width=qr_size, height=qr_size)

        name_text = (u.name or '').strip()
        seat_text = str(u.seat_no or '-').strip()
        slno_text = str(u.slno or '').strip()
        # Format: SL No  Name (line 1)  Seat: X (line 2)
        label = '{} {}<br/>Seat: {}'.format(slno_text, name_text, seat_text)
        para = Paragraph(label, label_style)
        all_cells.append([rl_img, para])

    # Pad to fill last row
    while len(all_cells) % COLS != 0:
        all_cells.append([Paragraph('', label_style), Paragraph('', label_style)])

    # Alternate: image row then label row
    table_rows = []
    for i in range(0, len(all_cells), COLS):
        chunk = all_cells[i:i + COLS]
        table_rows.append([c[0] for c in chunk])   # QR image row
        table_rows.append([c[1] for c in chunk])   # Label row

    # Image rows taller, label rows just enough for 2 lines of text
    row_heights = []
    for i in range(len(table_rows)):
        row_heights.append(qr_size + 4 * mm if i % 2 == 0 else 12 * mm)

    table = Table(table_rows, colWidths=[cell_w] * COLS, rowHeights=row_heights)
    table.setStyle(TableStyle([
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('INNERGRID',     (0, 0), (-1, -1), 0.4, colors.HexColor('#dddddd')),
        ('BOX',           (0, 0), (-1, -1), 0.6, colors.HexColor('#999999')),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING',   (0, 0), (-1, -1), 2),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 2),
    ]))

    doc = SimpleDocTemplate(
        response, pagesize=A4,
        rightMargin=PAGE_MARGIN, leftMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN, bottomMargin=PAGE_MARGIN,
        title="All_QR_Codes"
    )
    doc.build([table])
    return response


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

    # Rows for the split tables (these respect the applied filters)
    do_records = [r for r in records if r['user'].category and r['user'].category.upper() == 'DO']
    pb_records = [r for r in records if r['user'].category and r['user'].category.upper() == 'PB']
    lp_records = [r for r in records if r['user'].category and r['user'].category.upper() == 'LP']
    nom_records = [r for r in records if r['user'].category and r['user'].category.upper() == 'NOM']
    other_records = [r for r in records if not r['user'].category or r['user'].category.upper() not in ['DO', 'PB', 'LP', 'NOM']]

    # Calculate GLOBAL stats for the summary table (ignoring current filters)
    global_users = User.objects.all()
    total_del = global_users.count()
    present_del = AttendanceRecord.objects.filter(scan_time__date=report_date).values('user').distinct().count()
    absent_del = total_del - present_del

    global_do = global_users.filter(category__iexact='DO')
    total_do = global_do.count()
    present_do = AttendanceRecord.objects.filter(scan_time__date=report_date, user__category__iexact='DO').values('user').distinct().count()
    absent_do = total_do - present_do
    
    global_pb = global_users.filter(category__iexact='PB')
    total_pb = global_pb.count()
    present_pb = AttendanceRecord.objects.filter(scan_time__date=report_date, user__category__iexact='PB').values('user').distinct().count()
    absent_pb = total_pb - present_pb
    
    global_lp = global_users.filter(category__iexact='LP')
    total_lp = global_lp.count()
    present_lp = AttendanceRecord.objects.filter(scan_time__date=report_date, user__category__iexact='LP').values('user').distinct().count()
    absent_lp = total_lp - present_lp

    global_nom = global_users.filter(category__iexact='NOM')
    total_nom = global_nom.count()
    present_nom = AttendanceRecord.objects.filter(scan_time__date=report_date, user__category__iexact='NOM').values('user').distinct().count()
    absent_nom = total_nom - present_nom

    if export == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="CSI_MKD_Council_Attendance2026_{selected_date}.csv"'
        writer = csv.writer(response)
        
        writer.writerow(["CSI Madhya Kerala Diocese"])
        writer.writerow(["Diocesan Council 2026 - November 17, 18, 19"])
        writer.writerow([f"Attendance Report - {selected_date}"])
        writer.writerow([])
        
        counter = 1
        if do_records:
            writer.writerow(['DIOCESAN OFFICERS'])
            writer.writerow(['SL No', 'Name', 'Church', 'Constituency', 'Seat No', 'Status', 'Scan Time'])
            for row in do_records:
                st = row['scan_time']
                scan_str = timezone.localtime(st).strftime('%d %b %Y, %I:%M %p') if st else ''
                writer.writerow([
                    str(counter), row['user'].name,
                    row['user'].church, row['user'].constituency, row['user'].seat_no,
                    'Present' if row['attended'] else 'Absent',
                    scan_str
                ])
                counter += 1
            writer.writerow([])
            
        if pb_records:
            writer.writerow(['PRESBYTERS'])
            writer.writerow(['SL No', 'Name', 'Church', 'Constituency', 'Seat No', 'Status', 'Scan Time'])
            for row in pb_records:
                st = row['scan_time']
                scan_str = timezone.localtime(st).strftime('%d %b %Y, %I:%M %p') if st else ''
                writer.writerow([
                    str(counter), row['user'].name,
                    row['user'].church, row['user'].constituency, row['user'].seat_no,
                    'Present' if row['attended'] else 'Absent',
                    scan_str
                ])
                counter += 1
            writer.writerow([])
            
        if lp_records:
            writer.writerow(['LAYPERSONS'])
            writer.writerow(['SL No', 'Name', 'Church', 'Constituency', 'Seat No', 'Status', 'Scan Time'])
            for row in lp_records:
                st = row['scan_time']
                scan_str = timezone.localtime(st).strftime('%d %b %Y, %I:%M %p') if st else ''
                writer.writerow([
                    str(counter), row['user'].name,
                    row['user'].church, row['user'].constituency, row['user'].seat_no,
                    'Present' if row['attended'] else 'Absent',
                    scan_str
                ])
                counter += 1
            writer.writerow([])

        if nom_records:
            writer.writerow(['BISHOP NOMINEES'])
            writer.writerow(['SL No', 'Name', 'Church', 'Constituency', 'Seat No', 'Status', 'Scan Time'])
            for row in nom_records:
                st = row['scan_time']
                scan_str = timezone.localtime(st).strftime('%d %b %Y, %I:%M %p') if st else ''
                writer.writerow([
                    str(counter), row['user'].name,
                    row['user'].church, row['user'].constituency, row['user'].seat_no,
                    'Present' if row['attended'] else 'Absent',
                    scan_str
                ])
                counter += 1
            writer.writerow([])

        if other_records:
            writer.writerow(['OTHER DELEGATES'])
            writer.writerow(['SL No', 'Name', 'Church', 'Constituency', 'Seat No', 'Status', 'Scan Time'])
            for row in other_records:
                st = row['scan_time']
                scan_str = timezone.localtime(st).strftime('%d %b %Y, %I:%M %p') if st else ''
                writer.writerow([
                    str(counter), row['user'].name,
                    row['user'].church, row['user'].constituency, row['user'].seat_no,
                    'Present' if row['attended'] else 'Absent',
                    scan_str
                ])
                counter += 1
            writer.writerow([])
            
        writer.writerow(["Total delegates :", str(total_del)])
        writer.writerow(["Present :", str(present_del)])
        writer.writerow(["Absent :", str(absent_del)])
        writer.writerow([])
        if total_do > 0:
            writer.writerow(["Total Diocesan Officers :", str(total_do)])
            writer.writerow(["Present :", str(present_do)])
            writer.writerow(["Absent :", str(absent_do)])
            writer.writerow([])
        writer.writerow(["Total Presbyters :", str(total_pb)])
        writer.writerow(["Present :", str(present_pb)])
        writer.writerow(["Absent :", str(absent_pb)])
        writer.writerow([])
        writer.writerow(["Total LayPersons :", str(total_lp)])
        writer.writerow(["Present :", str(present_lp)])
        writer.writerow(["Absent :", str(absent_lp)])
        writer.writerow([])
        if total_nom > 0:
            writer.writerow(["Total Bishop Nominees :", str(total_nom)])
            writer.writerow(["Present :", str(present_nom)])
            writer.writerow(["Absent :", str(absent_nom)])
        
        return response
        
    elif export == 'pdf':
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, KeepTogether
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="CSI_MKD_Council_Attendance2026_{selected_date}.pdf"'
        
        doc = SimpleDocTemplate(response, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30, title=f"CSI_MKD_Council_Attendance2026_{selected_date}")
        elements = []
        
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'MainTitle',
            parent=styles['Title'],
            fontSize=14,
            leading=18,
            spaceAfter=6,
            textColor=colors.HexColor('#1e293b')
        )
        subtitle_style = ParagraphStyle(
            'SubTitle',
            parent=styles['Normal'],
            fontSize=11,
            leading=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#475569'),
            spaceAfter=15
        )
        
        styleN = ParagraphStyle('TableCell', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)
        
        table_heading_style = ParagraphStyle(
            'TableHeading',
            parent=styles['Normal'],
            spaceBefore=15,
            spaceAfter=20,
            fontSize=13,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#0f172a')
        )
        
        elements.append(Paragraph("<b>CSI Madhya Kerala Diocese</b>", title_style))
        elements.append(Paragraph(f"Diocesan Council 2026 - November 17, 18, 19<br/><b>Attendance Report - {selected_date}</b>", subtitle_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=20, spaceBefore=0))
        
            
        elements.append(Spacer(1, 10))
        
        base_table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')), 
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#334155')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ])
        col_widths = [30, 130, 100, 75, 45, 45, 110]
        
        counter = 1
        table_headers = ['SL No', 'Name', 'Church', 'Constituency', 'Seat No', 'Status', 'Scan Time']
        
        # 1. DO Table (or VIP Table fallback)
        if do_records:
            do_table_data = [table_headers]
            for row in do_records:
                st = row['scan_time']
                scan_str = timezone.localtime(st).strftime('%d %b %Y, %I:%M %p') if st else '-'
                do_table_data.append([
                    str(counter), 
                    Paragraph(str(row['user'].name or '-'), styleN),
                    Paragraph(str(row['user'].church or '-'), styleN),
                    Paragraph(str(row['user'].constituency or '-'), styleN),
                    str(row['user'].seat_no or '-'),
                    'Present' if row['attended'] else 'Absent',
                    scan_str
                ])
                counter += 1
            
            do_table = Table(do_table_data, colWidths=col_widths, repeatRows=1)
            do_table.setStyle(base_table_style)
            elements.append(Paragraph("<b>DIOCESAN OFFICERS</b>", table_heading_style))
            elements.append(do_table)
            elements.append(Spacer(1, 20))
        
        # 2. Presbyters Table
        if pb_records:
            pb_table_data = [table_headers]
            for row in pb_records:
                st = row['scan_time']
                scan_str = timezone.localtime(st).strftime('%d %b %Y, %I:%M %p') if st else '-'
                pb_table_data.append([
                    str(counter), 
                    Paragraph(str(row['user'].name or '-'), styleN),
                    Paragraph(str(row['user'].church or '-'), styleN),
                    Paragraph(str(row['user'].constituency or '-'), styleN),
                    str(row['user'].seat_no or '-'),
                    'Present' if row['attended'] else 'Absent',
                    scan_str
                ])
                counter += 1
            
            pb_table = Table(pb_table_data, colWidths=col_widths, repeatRows=1)
            pb_table.setStyle(base_table_style)
            elements.append(Paragraph("<b>PRESBYTERS</b>", table_heading_style))
            elements.append(pb_table)
            elements.append(Spacer(1, 20))
            
        # 3. LayPersons Table
        if lp_records:
            lp_table_data = [table_headers]
            for row in lp_records:
                st = row['scan_time']
                scan_str = timezone.localtime(st).strftime('%d %b %Y, %I:%M %p') if st else '-'
                lp_table_data.append([
                    str(counter), 
                    Paragraph(str(row['user'].name or '-'), styleN),
                    Paragraph(str(row['user'].church or '-'), styleN),
                    Paragraph(str(row['user'].constituency or '-'), styleN),
                    str(row['user'].seat_no or '-'),
                    'Present' if row['attended'] else 'Absent',
                    scan_str
                ])
                counter += 1
            
            lp_table = Table(lp_table_data, colWidths=col_widths, repeatRows=1)
            lp_table.setStyle(base_table_style)
            elements.append(Paragraph("<b>LAYPERSONS</b>", table_heading_style))
            elements.append(lp_table)
            elements.append(Spacer(1, 20))

        # 4. Bishop Nominees Table
        if nom_records:
            nom_table_data = [table_headers]
            for row in nom_records:
                st = row['scan_time']
                scan_str = timezone.localtime(st).strftime('%d %b %Y, %I:%M %p') if st else '-'
                nom_table_data.append([
                    str(counter), 
                    Paragraph(str(row['user'].name or '-'), styleN),
                    Paragraph(str(row['user'].church or '-'), styleN),
                    Paragraph(str(row['user'].constituency or '-'), styleN),
                    str(row['user'].seat_no or '-'),
                    'Present' if row['attended'] else 'Absent',
                    scan_str
                ])
                counter += 1
            
            nom_table = Table(nom_table_data, colWidths=col_widths, repeatRows=1)
            nom_table.setStyle(base_table_style)
            elements.append(Paragraph("<b>BISHOP NOMINEES</b>", table_heading_style))
            elements.append(nom_table)
            elements.append(Spacer(1, 20))

        # 5. Other Delegates Table
        if other_records:
            other_table_data = [table_headers]
            for row in other_records:
                st = row['scan_time']
                scan_str = timezone.localtime(st).strftime('%d %b %Y, %I:%M %p') if st else '-'
                other_table_data.append([
                    str(counter), 
                    Paragraph(str(row['user'].name or '-'), styleN),
                    Paragraph(str(row['user'].church or '-'), styleN),
                    Paragraph(str(row['user'].constituency or '-'), styleN),
                    str(row['user'].seat_no or '-'),
                    'Present' if row['attended'] else 'Absent',
                    scan_str
                ])
                counter += 1
            
            other_table = Table(other_table_data, colWidths=col_widths, repeatRows=1)
            other_table.setStyle(base_table_style)
            elements.append(Paragraph("<b>OTHER DELEGATES</b>", table_heading_style))
            elements.append(other_table)
            elements.append(Spacer(1, 20))

        summary_title = Paragraph("<b>Attendance Summary</b>", ParagraphStyle('SummaryTitle', parent=styles['Normal'], fontSize=11, spaceAfter=10, alignment=TA_CENTER, textColor=colors.HexColor('#0f172a')))

        summary_data = [
            ['Category', 'Total', 'Present', 'Absent'],
            ['All Delegates', str(total_del), str(present_del), str(absent_del)],
        ]
        if total_do > 0:
            summary_data.append(['Diocesan Officers', str(total_do), str(present_do), str(absent_do)])
        summary_data.extend([
            ['Presbyters', str(total_pb), str(present_pb), str(absent_pb)],
            ['LayPersons', str(total_lp), str(present_lp), str(absent_lp)],
        ])
        if total_nom > 0:
            summary_data.append(['Bishop Nominees', str(total_nom), str(present_nom), str(absent_nom)])

        summary_table = Table(summary_data, colWidths=[120, 80, 80, 80])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (0, -1), 10),
        ]))

        elements.append(KeepTogether([summary_title, summary_table]))
        doc.build(elements)
        return response

    churches = User.objects.values_list('church', flat=True).distinct().exclude(church__isnull=True).exclude(church='')
    cats = list(User.objects.values_list('category', flat=True).distinct().exclude(category__isnull=True).exclude(category=''))
    categories = sorted(cats, key=lambda c: 0 if c.upper() == 'DO' else (1 if c.upper() == 'PB' else (2 if c.upper() == 'LP' else (3 if c.upper() == 'NOM' else 4))))
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

@user_passes_test(is_admin_or_super, login_url='/accounts/login/')
def reset_all_attendance(request):
    """Remove today's attendance for ALL delegates."""
    if request.method == 'POST':
        date_str = request.POST.get('date', str(timezone.localdate()))
        try:
            from datetime import datetime
            reset_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            reset_date = timezone.localdate()
        AttendanceRecord.objects.filter(scan_time__date=reset_date).delete()
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
