from fastapi import (FastAPI, BackgroundTasks, UploadFile, 
                    File, Form, Depends, HTTPException, status, Request, Query)
from tortoise.contrib.fastapi import register_tortoise
from tortoise.exceptions import DoesNotExist
from models import (User, Business, Product, user_pydantic, user_pydanticIn,
                    product_pydantic, product_pydanticIn, business_pydantic,
                    business_pydanticIn, user_pydanticOut, Resep, resep_pydantic, resep_pydanticIn, Category, category_pydantic, category_pydanticIn, Beli, beli_pydantic, beli_pydanticIn,
                    Transaksi, transaksi_pydantic, transaksi_pydanticIn)
from tortoise.signals import  post_save 
from typing import List, Optional, Type
from tortoise import BaseDBAsyncClient, Model
from datetime import datetime
from starlette.responses import JSONResponse
from starlette.requests import Request
import jwt
from datetime import date
from tortoise.expressions import F
from tortoise.functions import Sum
from dotenv import dotenv_values
from fastapi.security import (
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm
)
from emails import *
from authentication import *
from dotenv import dotenv_values
import math
from fastapi import File, UploadFile
import secrets
from fastapi.staticfiles import StaticFiles
from PIL import Image
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from tortoise.transactions import in_transaction

config_credentials = dict(dotenv_values(".env"))

app = FastAPI(
    title="Warung Omega API: E-commerce Seafood Restaurant",
    version="3,14"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

oath2_scheme = OAuth2PasswordBearer(tokenUrl = 'token')

@app.post('/token')
async def generate_token(request_form: OAuth2PasswordRequestForm = Depends()):
    token = await token_generator(request_form.username, request_form.password)
    user = await User.get(username=request_form.username)

    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="Authorization", value=f"Bearer {token}", httponly=True)
    response.set_cookie(key="Username", value=user.username, httponly=True)
    return response

    # return {"access_token": token, "token_type": "bearer"}

@post_save(User)
async def create_business(
    sender: "Type[User]",
    instance: User,
    created: bool,
    using_db: "Optional[BaseDBAsyncClient]",
    update_fields: List[str]) -> None:
    
    if created:
        business_obj = await Business.create(
                business_name = instance.username, owner = instance)
        await business_pydantic.from_tortoise_orm(business_obj)
        await send_email([instance.email], instance)


@app.post('/registration')
async def user_registration(user: user_pydanticIn):
    user_info = user.dict(exclude_unset=True)
    user_info['password'] = get_password_hash(user_info['password'])
    user_obj = await User.create(**user_info)
    new_user = await user_pydantic.from_tortoise_orm(user_obj)
 
    await send_email([new_user.email], new_user)  # Send verification email
    
    return {
        "status": "ok",
        "data": f"Hello {new_user.username}, thanks for choosing our services. Please check your email inbox and click on the link to confirm your registration."
    }

templates = Jinja2Templates(directory="templates")

@app.get('/verification',  response_class=HTMLResponse)
async def email_verification(request: Request, token: str):
    user = await verify_token(token)
    if user and not user.is_verified:
        user.is_verified = True
        await user.save()
        return templates.TemplateResponse("verification.html", 
                                {"request": request, "username": user.username}
                        )
    raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED, 
            detail = "Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user(request: Request):
    token = request.cookies.get("Authorization")  # Ambil token dari cookie
    
    if token is None:
        # Token is not present, return None or handle it differently
        return None  # You can return None or a specific user object, depending on your flow
    
    token = token.split(" ")[1]  # Buang "Bearer" dan ambil hanya tokennya
    
    try:
        payload = jwt.decode(token, config_credentials['SECRET'], algorithms=['HS256'])
        user_id = payload.get("id")
        user = await User.get(id=user_id)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.post('/user/me')
async def user_login(user: user_pydantic = Depends(get_current_user)):

    business = await Business.get(owner = user)
    logo = business.logo
    logo = "localhost:8000/static/images/"+logo

    return {"status" : "ok", 
            "data" : 
                {
                    "username" : user.username,
                    "email" : user.email,
                    "verified" : user.is_verified,
                    "join_date" : user.join_date.strftime("%b %d %Y"),
                    "logo" : logo
                }
            }

@app.get('/logout')
async def logout(request: Request):
    response = RedirectResponse(url="/")
    response.delete_cookie("Authorization")  # Menghapus cookie token
    return response

@app.get('/contact', response_class=HTMLResponse)
async def contact_page(request: Request):
    user = await get_current_user(request)
    username = user.username
    id_user = user.id

    return templates.TemplateResponse("contact.html", {"request": request, "username": username, "id_user": id_user})


@app.get("/categories")
async def get_categories():
    response = await category_pydantic.from_queryset(Category.all())
    return {"status": "ok", "data": response}

@app.get("/categories/{id_category}")
async def get_category_by_id(id_category: int):
    category = await Category.get(id_category=id_category)
    if not category:
        return {"status": "error", "message": "Category not found"}
    
    response = await category_pydantic.from_tortoise_orm(category)
    return {"status": "ok", "data": response}

@app.post("/categories")
async def add_new_category(category: category_pydanticIn):
    category_obj = await Category.create(**category.dict(exclude_unset=True))
    response = await category_pydantic.from_tortoise_orm(category_obj)
    return {"status": "ok", "data": response}

@app.delete("/categories/{id_category}")
async def delete_category(id_category: int):
    category = await Category.get(id_category=id_category)
    if not category:
        return {"status": "error", "message": "Category not found"}
    
    await category.delete()
    return {"status": "ok", "message": "Category deleted successfully"}

class ProductCreate(BaseModel):
    name: str
    original_price: float
    new_price: float
    offer_expiration_date: date
    harga_note: str
    produk_note: str
    lokasi: str
    product_description: Optional[str] = None
    tips: Optional[str] = None
    id_category: int


@app.post("/products")
async def add_new_product(product: ProductCreate, user: user_pydantic = Depends(get_current_user)):
    product_dict = product.dict()
    
    # Ambil id_category dari data
    category_id = product_dict.pop('id_category')  # Ambil id_category dari dictionary dan hapus dari data
    
    try:
        category = await Category.get(id_category=category_id)
    except Category.DoesNotExist:
        return {"status": "error", "message": "Category not found"}
    
    # Tambahkan id_category ke dalam dictionary produk
    if 'original_price' in product_dict and product_dict['original_price'] > 0:
        product_dict["percentage_discount"] = ((product_dict["original_price"] - product_dict['new_price']) / product_dict['original_price']) * 100


    product_obj = await Product.create(
        **product_dict,
        business=user,
        category=category  
    )
    product_obj = await product_pydantic.from_tortoise_orm(product_obj)
    
    return {"status": "ok", "data": product_obj}

# get products but without id specified
@app.get("/products")
async def get_products():
    response = await product_pydantic.from_queryset(Product.all())
    return {"status": "ok", "data": response}

@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    user = await get_current_user(request)
    
    # Check if user is None and handle the login logic
    if user is None:
        return templates.TemplateResponse("index.html", {"request": request, "products": [], "username": None, "id_user": None})
    
    username = user.username
    id_user = user.id

    # Mengambil 6 produk dari database sebagai objek model ORM
    products = await Product.all().limit(6).order_by("id")
    products_data = [await product_pydantic.from_tortoise_orm(product) for product in products]  # Proses per item
    
    return templates.TemplateResponse("index.html", {"request": request, "products": products_data, "username": username, "id_user": id_user})

@app.get("/products-page", response_class=HTMLResponse)
async def products_page(request: Request, page: int = 1, id_category: int = None):
    user = await get_current_user(request)
    username = user.username
    id_user = user.id

    per_page = 6
    start = (page - 1) * per_page
    end = start + per_page

    # Jika id_category diberikan, filter berdasarkan id_category
    if id_category:
        products = await Product.filter(category_id=id_category).limit(per_page).offset(start)
        total_products = await Product.filter(category_id=id_category).count()
    else:
        products = await Product.all().limit(per_page).offset(start)
        total_products = await Product.all().count()

    total_pages = (total_products + per_page - 1) // per_page
    products_data = [await product_pydantic.from_tortoise_orm(product) for product in products]

    categories = await Category.all()  # Untuk daftar kategori pada sidebar filter
    return templates.TemplateResponse(
        "products.html", 
        {
            "request": request,
            "username": username,
            "products": products_data, 
            "page": page, 
            "total_pages": total_pages, 
            "categories": categories, 
            "selected_category": id_category,  # Untuk mengetahui kategori yang dipilih
            "id_user": id_user
        }
    )


@app.get("/products/{id}")
async def specific_product(id: int):
    product = await Product.get(id=id)
    business = await product.business
    owner = await business.owner
    category = await product.category  # Dapatkan kategori produk
    
    response = await product_pydantic.from_queryset_single(Product.get(id=id))
    
    return {
        "status": "ok",
        "data": {
            "product_details": response,
            "business_details": {
                "name": business.business_name,
                "city": business.city,
                "region": business.region,
                "description": business.business_description,
                "logo": business.logo,
                "owner_id": owner.id,
                "email": owner.email,
                "join_date": owner.join_date.strftime("%b %d %Y")
            },
            "category_details": {
                "id_category": category.id_category,
                "category_name": category.category_name
            }
        }
    }


@app.delete("/products/{id}")
async def delete_product(id: int, user: user_pydantic = Depends(get_current_user)):
    product = await Product.get(id=id)
    business = await product.business
    owner = await business.owner
    if owner == user:
        await product.delete()
        return {"status": "ok"}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated to perform this action",
            headers={"WWW-Authenticate": "Bearer"},
        )

@app.get("/products-detail/{id}", response_class=HTMLResponse)
async def product_detail(request: Request, id: int):
    user = await get_current_user(request)
    username = user.username
    id_user = user.id

    try:
        product = await Product.get(id=id)
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Product not found")

    # Ambil data business dan category jika dibutuhkan
    business = await product.business
    owner = await business.owner
    category = await product.category

    # Return halaman detail produk dengan data produk
    return templates.TemplateResponse(
        "product-detail.html", 
        {
            "request": request,
            "username": username,
            "product": product,
            "business": business,
            "owner": owner,
            "category": category,
            "id_user": id_user
        }
    )

@app.put("/product/{id}")
async def update_product(id: int, update_info: product_pydanticIn, user: user_pydantic = Depends(get_current_user)):
    product = await Product.get(id=id)
    business = await product.business
    owner = await business.owner

    # Memperbaiki penulisan 'exclude_unset'
    update_info = update_info.dict(exclude_unset=True)
    update_info["date_published"] = datetime.utcnow()
    
    if user == owner and update_info["original_price"] > 0:
        update_info["percentage_discount"] = ((update_info["original_price"] - update_info['new_price']) / update_info['original_price']) * 100

        # Memperbarui objek produk
        await product.update_from_dict(update_info)
        await product.save()

        response = await product_pydantic.from_tortoise_orm(product)
        return {"status": "ok", "data": response}
    
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated to perform this action or invalid user input",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.post("/reseps")
async def add_new_resep(resep: resep_pydanticIn):
    resep_info = resep.dict(exclude_unset=True)
    resep_obj = await Resep.create(**resep_info)
    resep_obj = await resep_pydantic.from_tortoise_orm(resep_obj)
    return {"status": "ok", "data": resep_obj}

# Get all reseps
@app.get("/reseps")
async def get_reseps():
    response = await resep_pydantic.from_queryset(Resep.all())
    return {"status": "ok", "data": response}

@app.get("/reseps-page", response_class=HTMLResponse)
async def reseps_page(request: Request, page: int = 1):
    user = await get_current_user(request)
    username = user.username
    id_user = user.id

    per_page = 6  # Jumlah item per halaman
    start = (page - 1) * per_page
    end = start + per_page

    # Ambil semua resep dan hitung total resep
    reseps = await Resep.all().limit(per_page).offset(start)
    total_reseps = await Resep.all().count()

    # Hitung total halaman
    total_pages = (total_reseps + per_page - 1) // per_page
    reseps_data = [await resep_pydantic.from_tortoise_orm(resep) for resep in reseps]

    # Kirim ke template resep.html
    return templates.TemplateResponse(
        "resep.html",
        {
            "request": request,
            "username": username,
            "reseps": reseps_data,
            "page": page,
            "total_pages": total_pages,
            "id_user": id_user
        }
    )

@app.get("/reseps-detail/{id}", response_class=HTMLResponse)
async def resep_detail(request: Request, id: int):
    user = await get_current_user(request)
    username = user.username
    id_user = user.id

    try:
        resep = await Resep.get(id=id)
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Resep was not found")
    
    return templates.TemplateResponse(
        "resep-detail.html",
        {
            "request": request,
            "username": username,
            "resep": resep,
            "id_user": id_user
        }
    )


# Get detailed resep by id
@app.get("/reseps/{id}")
async def get_resep_by_id(id: int):
    try:
        resep = await Resep.get(id=id)
        response = await resep_pydantic.from_tortoise_orm(resep)
        return {"status": "ok", "data": response}
    except Resep.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resep not found",
        )

@app.delete("/reseps/{id}")
async def delete_resep(id: int):
    resep = await Resep.get(id=id)
    await resep.delete()
    return {"status": "ok"}
    
class BeliInput(BaseModel):
    produk_id: int
    kuantitas: int

@app.post("/belis")
async def create_beli(beli_input: BeliInput, user: user_pydantic = Depends(get_current_user)):
    # Retrieve product by ID
    produk = await Product.get(id=beli_input.produk_id)
    if not produk:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")

    # Calculate harga_total
    harga_total = produk.new_price * beli_input.kuantitas

    # Create new Beli object
    beli_obj = await Beli.create(
        user_id=user.id,
        product_id=produk.id,
        kuantitas=beli_input.kuantitas,
        harga_total=harga_total
    )

    return {"status": "ok", "data": await beli_pydantic.from_tortoise_orm(beli_obj)}

@app.get("/belis/me", response_class=HTMLResponse)
async def get_my_belis(request: Request):
    user = await get_current_user(request)
    username = user.username
    id_user = user.id

    belis = await Beli.filter(user=user).select_related('product')

    beli_list = []
    for beli in belis:
        product = beli.product
        beli_data = {
            "beli_id": beli.id_beli,
            "kuantitas": beli.kuantitas,
            "harga_total": beli.harga_total,
            "product": {
                "id": product.id,
                "name": product.name,
                "original_price": product.original_price,
                "new_price": product.new_price,
                "percentage_discount": product.percentage_discount,
                "product_description": product.product_description,
                "product_image": product.product_image,
            }
        }
        beli_list.append(beli_data)
    
    username = user.username

    response = templates.TemplateResponse(
        "beli.html",
        {
            "request": request,
            "beli_list": beli_list,
            "username": username,
            "id_user": id_user
        }
    )
    # response.set_cookie(key="Authorization", value=f"Bearer {token}", httponly=True)
    return response

@app.delete("/belis/{beli_id}/hapus")
async def hapus_beli(beli_id: int, current_user: User = Depends(get_current_user)):
    beli = await Beli.get(id=beli_id, user_id=current_user.id)
    if not beli:
        raise HTTPException(status_code=404, detail="Item tidak ditemukan")
    await beli.delete()
    return {"status": "ok"}


@app.get("/belis/{id_beli}")
async def get_beli_by_id(id_beli: int):
    # Retrieve Beli by ID
    beli = await Beli.get(id_beli=id_beli).select_related('product', 'user')
    if not beli:
        raise HTTPException(status_code=404, detail="Beli tidak ditemukan")

    # Convert to Pydantic model
    beli_details = await beli_pydantic.from_tortoise_orm(beli)

    # Access product details
    product = beli.product  # This retrieves the related product
    user = beli.user

    # Prepare response
    response_data = {
        "status": "ok",
        "data": {
            "beli_details": beli_details,
            "product": {
                "id": product.id,
                "name": product.name,
                "original_price": product.original_price,
                "new_price": product.new_price,
                "percentage_discount": product.percentage_discount,
                "product_description": product.product_description
            },  # <--- added a comma here
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email
            }
        }  # <--- added a closing bracket here
    }

    return response_data


@app.get("/belis", response_model=List[beli_pydantic])
async def get_belis(user: user_pydantic = Depends(get_current_user)):
    # Retrieve all Beli for the current user
    belis = await Beli.filter(user=user).select_related('product')
    return belis

@app.delete("/belis/{id_beli}")
async def delete_beli(id_beli: int):
    # Retrieve Beli by ID
    beli = await Beli.get(id_beli=id_beli)
    if not beli:
        raise HTTPException(status_code=404, detail="Beli tidak ditemukan")

    # Delete the Beli
    await beli.delete()
    return {"status": "ok", "message": "Beli berhasil dihapus"}

class TransaksiInput(BaseModel):
    total: float

@app.post("/transaksis")
async def create_transaksi(transaksi_input: TransaksiInput,
                           user: user_pydantic = Depends(get_current_user)):
    
    belis = await Beli.filter(user=user).select_related('product')
    if not belis:
        raise HTTPException(status_code=404, detail="Tidak ada beli yang ditemukan")
    
    # transaksi baru objek
    transaksi_obj = await Transaksi.create(
        user_id = user.id,
        total = transaksi_input.total,
    )

    for beli in belis:
        await transaksi_obj.belis.add(beli)

    return {"status": "ok",
            "data": await transaksi_pydantic.from_tortoise_orm(transaksi_obj)}

@app.get("/transaksis", response_model=List[transaksi_pydantic])
async def get_transaksis(user: user_pydantic = Depends(get_current_user)):
    transaksis = await Transaksi.filter(user=user).prefetch_related('belis')
    return transaksis

@app.delete("/transaksis/{id_transaksi}")
async def delete_transaksi(id_transaksi: int,
                           user: user_pydantic = Depends(get_current_user)):
    
    transaksi = await Transaksi.get(id_transaksi=id_transaksi, user=user)

    if not transaksi:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan")
    
    # delete transaaction
    await transaksi.delete()
    return {"status": "ok",
            "message": "Transaction deleted successfully"}

@app.get("/transaksis/{id_transaksi}", response_class=JSONResponse)
async def get_transaksi_by_id(id_transaksi: int, user: user_pydantic = Depends(get_current_user)):
    # Cek apakah transaksi dengan id tersebut ada dan milik user yang sedang login
    try:
        transaksi = await Transaksi.get(id_transaksi=id_transaksi, user=user).prefetch_related('belis')
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan")

    # Ambil semua beli yang terhubung dengan transaksi tersebut
    belis = transaksi.belis

    # List untuk menyimpan detail transaksi
    beli_list = []
    for beli in belis:
        product = await beli.product

        # Append data beli dan produk terkait
        beli_data = {
            "beli_id": beli.id_beli,
            "kuantitas": beli.kuantitas,
            "harga_total": beli.harga_total,
            "product": {
                "id": product.id,
                "name": product.name,
                "original_price": product.original_price,
                "new_price": product.new_price,
                "percentage_discount": product.percentage_discount,
                "product_description": product.product_description
            }
        }
        beli_list.append(beli_data)

    # Siapkan respon JSON dengan detail transaksi
    transaksi_data = {
        "id_transaksi": transaksi.id_transaksi,
        "total": transaksi.total,
        "status": transaksi.status,
        "belis": beli_list
    }

    return {"status": "ok", "data": transaksi_data}


# image upload
@app.post("/uploadfile/profile")
async def create_upload_file(file: UploadFile = File(...), user: user_pydantic = Depends(get_current_user)):
    FILEPATH = "./static/images/"
    filename = file.filename
    extension = filename.split(".")[1]

    if extension not in ["jpg", "png"]:
        return {"status" : "error", "detail" : "file extension not allowed"}

    token_name = secrets.token_hex(10)+"."+extension
    generated_name = FILEPATH + token_name
    file_content = await file.read()
    with open(generated_name, "wb") as file:
        file.write(file_content)

    img = Image.open(generated_name)
    img = img.resize(size = (200,200))
    img.save(generated_name)

    file.close()

    business = await Business.get(owner = user)
    owner = await business.owner

    print(user.id)
    print(owner.id)
    if owner == user:
        business.logo = token_name
        await business.save()
    
    else:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED, 
            detail = "Not authenticated to perform this action",
            headers={"WWW-Authenticate": "Bearer"},
        )
    file_url = "localhost:8000" + generated_name[1:]
    return {"status": "ok", "filename": file_url}


@app.post("/uploadfile/product/{id}")
async def create_upload_file(id: int, file: UploadFile = File(...), user: user_pydantic = Depends(get_current_user)):
    FILEPATH = "./static/images/"
    filename = file.filename
    extension = filename.split(".")[1]

    if extension not in ["jpg", "png"]:
        return {"status" : "error", "detail" : "file extension not allowed"}

    token_name = secrets.token_hex(10)+"."+extension
    generated_name = FILEPATH + token_name
    file_content = await file.read()
    with open(generated_name, "wb") as file:
        file.write(file_content)

    img = Image.open(generated_name)
    img = img.resize(size = (200,200))
    img.save(generated_name)

    file.close()
    product = await Product.get(id = id)
    business = await product.business
    owner = await business.owner

    if owner == user:
        product.product_image = token_name
        await product.save()
    
    else:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED, 
            detail = "Not authenticated to perform this action",
            headers={"WWW-Authenticate": "Bearer"},
        )


    file_url = "localhost:8000" + generated_name[1:]
    return {"status": "ok", "filename": file_url}

@app.post("/uploadfile/resep/{id}")
async def upload_resep_image(id: int, file: UploadFile = File(...), user: user_pydantic = Depends(get_current_user)):
    FILEPATH = "./static/images/"
    filename = file.filename
    extension = filename.split(".")[1]

    if extension not in ["jpg", "png"]:
        return {"status": "error", "detail": "File extension not allowed"}

    token_name = secrets.token_hex(10) + "." + extension
    generated_name = FILEPATH + token_name
    file_content = await file.read()
    with open(generated_name, "wb") as file:
        file.write(file_content)

    img = Image.open(generated_name)
    img = img.resize(size=(200, 200))
    img.save(generated_name)

    file.close()

    resep = await Resep.get(id=id)
    
    # Implement ownership check if needed (e.g., check if the user has permission to upload an image for this recipe)
    resep.gambar_resep = token_name
    await resep.save()

    file_url = "localhost:8000" + generated_name[1:]
    return {"status": "ok", "filename": file_url}

@app.post("/uploadfile/resep/{id}")
async def upload_resep_image(id: int, file: UploadFile = File(...), user: user_pydantic = Depends(get_current_user)):
    FILEPATH = "./static/images/"
    filename = file.filename
    extension = filename.split(".")[-1]

    if extension not in ["jpg", "png"]:
        return {"status": "error", "detail": "file extension not allowed"}

    token_name = secrets.token_hex(10) + "." + extension
    generated_name = FILEPATH + token_name
    file_content = await file.read()
    with open(generated_name, "wb") as f:
        f.write(file_content)

    img = Image.open(generated_name)
    img = img.resize(size=(200, 200))
    img.save(generated_name)

    file.close()
    try:
        resep = await Resep.get(id=id)
        if user.is_authenticated:
            resep.gambar_resep = token_name
            await resep.save()
            file_url = "localhost:8000" + generated_name[1:]
            return {"status": "ok", "filename": file_url}
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated to perform this action",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except Resep.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resep not found",
        )

register_tortoise(
    app,
    db_url='postgres://postgres:admin@localhost:5432/omega_db3',
    modules={'models': ['models']},
    generate_schemas=True,
    add_exception_handlers=True
)