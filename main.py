from fastapi import (FastAPI, BackgroundTasks, UploadFile, 
                    File, Form, Depends, HTTPException, status, Request, Query)
from tortoise.contrib.fastapi import register_tortoise
from tortoise.exceptions import DoesNotExist
from models import (User, Business, Product, user_pydantic, user_pydanticIn,
                    product_pydantic, product_pydanticIn, business_pydantic,
                    business_pydanticIn, user_pydanticOut, Resep, resep_pydantic, resep_pydanticIn,
                    Pesan, pesan_pydantic, pesan_pydanticIn, Cart, cart_pydantic, cart_pydanticIn,
                    Transaction, transaction_pydantic, transaction_pydanticIn, Report, report_pydantic,
                    report_pydanticIn, Category, category_pydantic, category_pydanticIn)
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
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from tortoise.transactions import in_transaction

config_credentials = dict(dotenv_values(".env"))


app = FastAPI(
    title="Warung Omega API: E-commerce Seafood Restaurant",
    version="3,14"
)

app.mount("/static", StaticFiles(directory="static"), name="static")

oath2_scheme = OAuth2PasswordBearer(tokenUrl = 'token')

@app.post('/token')
async def generate_token(request_form: OAuth2PasswordRequestForm = Depends()):
    token = await token_generator(request_form.username, request_form.password)
    response = JSONResponse(content={'access_token': token, 'token_type': 'bearer'})
    response.set_cookie(key="Authorization", value=f"Bearer {token}")
    return response



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
    user_info = user.dict(exclude_unset = True)
    user_info['password'] = get_password_hash(user_info['password'])
    user_obj = await User.create(**user_info)
    new_user = await user_pydantic.from_tortoise_orm(user_obj)
 
    return {"status" : "ok", 
            "data" : 
                f"Hello {new_user.username} thanks for choosing our services. Please check your email inbox and click on the link to confirm your registration."}

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


async def get_current_user(token: str = Depends(oath2_scheme)):
    try:
        payload = jwt.decode(token, config_credentials['SECRET'], algorithms = ['HS256'])
        user = await User.get(id = payload.get("id"))
    except:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED, 
            detail = "Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await user

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
    response.delete_cookie("Authorization")
    return response


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
    # Mengambil 6 produk dari database sebagai objek model ORM
    products = await Product.all().limit(6).order_by("id")
    products_data = [await product_pydantic.from_tortoise_orm(product) for product in products]  # Proses per item
    return templates.TemplateResponse("index.html", {"request": request, "products": products_data})

@app.get("/products-page", response_class=HTMLResponse)
async def products_page(request: Request, page: int = 1, id_category: int = None):
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
            "products": products_data, 
            "page": page, 
            "total_pages": total_pages, 
            "categories": categories, 
            "selected_category": id_category  # Untuk mengetahui kategori yang dipilih
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
            "reseps": reseps_data,
            "page": page,
            "total_pages": total_pages,
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
    

class PesanInput(BaseModel):
    produk_id: int
    kuantitas: int
    cart_id: int


@app.post("/pesans")
async def create_pesan(pesan_input: PesanInput, user: user_pydantic = Depends(get_current_user)):
    # Mendapatkan Cart berdasarkan cart_id
    try:
        cart = await Cart.get(cart_id=pesan_input.cart_id, user=user)
    except Cart.DoesNotExist:
        raise HTTPException(status_code=404, detail="Cart tidak ditemukan atau tidak sesuai")

    # Mendapatkan produk berdasarkan ID
    produk = await Product.get(id=pesan_input.produk_id)
    if not produk:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")

    # Menghitung harga_kuantitas
    harga_kuantitas = produk.new_price * pesan_input.kuantitas

    # Membuat Pesan baru
    pesan_obj = await Pesan.create(
        produk=produk,
        cart=cart,
        kuantitas=pesan_input.kuantitas,
        harga_kuantitas=harga_kuantitas
    )

    # Menghitung total harga baru pada Cart
    pesan_list = await Pesan.filter(cart=cart).values_list('harga_kuantitas', flat=True)
    total_harga = sum(pesan_list)

    # Update cart dengan harga_total baru
    cart.harga_total = total_harga
    await cart.save()

    return {"status": "ok", "data": await pesan_pydantic.from_tortoise_orm(pesan_obj)}


@app.get("/pesans/{id_pesan}")
async def specific_pesan(id_pesan: int):
    # Mendapatkan pesan berdasarkan id_pesan
    pesan = await Pesan.get(id_pesan=id_pesan).select_related('produk', 'cart')
    if not pesan:
        raise HTTPException(status_code=404, detail="Pesan tidak ditemukan")

    # Mendapatkan detail produk dan cart
    produk = await pesan.produk
    cart = await pesan.cart
    user = await cart.user

    # Membuat response
    pesan_details = await pesan_pydantic.from_queryset_single(Pesan.get(id_pesan=id_pesan))

    return {
        "status": "ok",
        "data": {
            "pesan_details": pesan_details,
            "produk_details": {
                "produk_id": produk.id,
                "nama_produk": produk.name,
                "kategori": produk.category,
                "harga": produk.new_price
            },
            "cart_details": {
                "cart_id": cart.cart_id,
                "user_id": user.id,
                "user_email": user.email,
                "harga_total": cart.harga_total
            }
        }
    }


@app.get("/pesans", response_model=List[pesan_pydantic])
async def get_pesans():
    # Mendapatkan semua Pesan
    pesans = await Pesan.all().select_related('produk', 'cart')  # Pastikan untuk mengikutkan relasi produk dan cart
    return pesans

@app.delete("/pesans/{pesan_id}")
async def delete_pesan(pesan_id: int):
    # Mencari Pesan berdasarkan ID
    pesan = await Pesan.get(id_pesan=pesan_id)
    if not pesan:
        raise HTTPException(status_code=404, detail="Pesan tidak ditemukan")

    # Menghapus Pesan
    await pesan.delete()
    return {"status": "ok", "message": "Pesan berhasil dihapus"}

@app.get("/carts")
async def get_carts():
    response = await cart_pydantic.from_queryset(Cart.all())
    return {"status": "ok", "data": response}

# Post Cart
@app.post("/carts")
async def create_cart(user: user_pydantic = Depends(get_current_user)):
    cart_obj = await Cart.create(user=user)
    return {"status": "ok", "data": await cart_pydantic.from_tortoise_orm(cart_obj)}
    

@app.delete("/carts/{cart_id}")
async def delete_cart(cart_id: int, user: user_pydantic = Depends(get_current_user)):
    cart = await Cart.get(cart_id=cart_id)
    if cart.user_id == user.id:
        await cart.delete()
        return {"status": "ok"}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated to perform this action",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Get Transaction
@app.get("/transactions")
async def get_transactions():
    response = await transaction_pydantic.from_queryset(Transaction.all())
    return {"status": "ok", "data": response}

@app.get("/transactions")
async def get_transactions():
    response = await transaction_pydantic.from_queryset(Transaction.all())
    return {"status": "ok", "data": response}

@app.get("/transactions/{id_transaction}")
async def specific_transaction(id_transaction: int):
    # Mendapatkan transaction berdasarkan id_transaction
    transaction = await Transaction.get(id_transaction=id_transaction).select_related('cart')
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction tidak ditemukan")

    # Mendapatkan detail cart
    cart = await transaction.cart
    user = await cart.user

    # Membuat response
    transaction_details = await transaction_pydantic.from_queryset_single(Transaction.get(id_transaction=id_transaction))

    return {
        "status": "ok",
        "data": {
            "transaction_details": transaction_details,
            "cart_details": {
                "cart_id": cart.cart_id,
                "user_id": user.id,
                "user_email": user.email,
                "harga_total": cart.harga_total
            }
        }
    }


@app.post("/transactions")
async def create_transaction(cart_id: int):
    # Mendapatkan Cart berdasarkan cart_id
    try:
        cart = await Cart.get(cart_id=cart_id)
    except Cart.DoesNotExist:
        raise HTTPException(status_code=404, detail="Cart tidak ditemukan")

    # Membuat Transaction baru
    transaction_obj = await Transaction.create(cart=cart)
    return {"status": "ok", "data": await transaction_pydantic.from_tortoise_orm(transaction_obj)}

@app.delete("/transactions/{transaction_id}")
async def delete_transaction(transaction_id: int):
    try:
        transaction = await Transaction.get(id_transaction=transaction_id)
        await transaction.delete()
        return {"status": "ok"}
    except Transaction.DoesNotExist:
        raise HTTPException(status_code=404, detail="Transaction tidak ditemukan")

@app.get("/reports")
async def get_reports():
    response = await report_pydantic.from_queryset(Report.all())
    return {"status": "ok", "data": response}

@app.post("/reports")
async def create_report(transaction_id: int):
    # Mendapatkan Transaction berdasarkan transaction_id
    try:
        transaction = await Transaction.get(id_transaction=transaction_id)
    except Transaction.DoesNotExist:
        raise HTTPException(status_code=404, detail="Transaction tidak ditemukan")

    # Membuat Report baru
    report_obj = await Report.create(transaction=transaction)
    return {"status": "ok", "data": await report_pydantic.from_tortoise_orm(report_obj)}

@app.get("/reports/{id_report}")
async def specific_report(id_report: int):
    # Mendapatkan report berdasarkan id_report
    report = await Report.get(id_report=id_report).select_related('transaction')
    if not report:
        raise HTTPException(status_code=404, detail="Report tidak ditemukan")

    # Mendapatkan detail transaction
    transaction = await report.transaction
    cart = await transaction.cart
    user = await cart.user

    # Membuat response
    report_details = await report_pydantic.from_queryset_single(Report.get(id_report=id_report))

    return {
        "status": "ok",
        "data": {
            "report_details": report_details,
            "transaction_details": {
                "transaction_id": transaction.id_transaction,
                "cart_id": cart.cart_id,
                "user_id": user.id,
                "user_email": user.email,
            }
        }
    }


@app.delete("/reports/{report_id}")
async def delete_report(report_id: int):
    try:
        report = await Report.get(id_report=report_id)
        await report.delete()
        return {"status": "ok"}
    except Report.DoesNotExist:
        raise HTTPException(status_code=404, detail="Report tidak ditemukan")


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